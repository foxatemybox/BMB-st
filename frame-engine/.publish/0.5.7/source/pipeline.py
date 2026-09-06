from __future__ import annotations

from dataclasses import replace

from PIL import Image, ImageOps

from badloom_manga.crop_background_profile import (
    PageBackgroundMode,
    PageBackgroundProfile,
)
from badloom_manga.crop_row_analysis import _dominant_border_colour

from .background import analyze_background
from .coarse_rows import detect_coarse_rows
from .contract import PageAnalysisResult
from .diagnostics import (
    DiagnosticsCollector,
    FanoutDiagnosticsCollector,
    ListDiagnosticsCollector,
    emit,
)
from .horizontal_split import split_horizontal_panels
from .ordering import assemble_candidates
from .row_rules import refine_rows_at_panel_rules
from .settings import FrameAnalysisSettings
from .side_refine import refine_panel_sides


ENGINE_API = "0.5"
ENGINE_VERSION = "0.5.7"
ENGINE_CHANGELOG = (
    "Финальный source-resolution X-refine теперь использует устойчивый canvas reference, согласованный с background-aware row mask, вместо медианы всего периметра длинной webtoon-страницы.",
    "На MIXED-странице с неоднозначным border dominance non-dark путь повторяет legacy light fallback маски; edge-touching artwork больше не должен приниматься за canvas и обрезать правую/левую внешнюю границу кадра.",
    "Диагностика side_refine фиксирует CANVAS_REFERENCE_RESOLVED с исходной и эффективной яркостью/spread, RGB, dominance, noise и выбранной стратегией.",
    "Оптимизирована диагностика 0.5: JSONL writer больше не выполняет mkdir/stat на каждое событие и восстанавливает каталог только при реальном удалении во время работы.",
    "Batch-страницы с одним trace path теперь переиспользуют общий diagnostics collector и общий append lock, уменьшая setup overhead и исключая независимые блокировки одного JSONL-файла.",
    "Формат JSONL и немедленная запись каждого diagnostic event сохранены; диагностика не буферизуется и не участвует во внутренних pixel/Y-scan циклах геометрии.",
    "Ускорен source-resolution поиск боковых границ: дорогой переход canvas→panel теперь использует ограниченную равномерную выборку Y и O(1) проверки X-кандидатов по prefix/run таблицам.",
    "На эталонной синтетической странице 1200×6000 локальный проход 0.5.4 сократился примерно с 11.1 до 2.0 секунды без изменения итоговых quad; CI дополнительно проверяет геометрию.",
    "Пакетный анализ BMB теперь сохраняет стабильный ID совпавшего кадра, но координаты, confidence и reason codes всегда берёт из свежего analyzer-owned результата.",
)


def _rgb_luminance(rgb: tuple[int, int, int]) -> float:
    red, green, blue = rgb
    return 0.2126 * float(red) + 0.7152 * float(green) + 0.0722 * float(blue)


def resolve_side_canvas_reference(
    source: Image.Image,
    background: PageBackgroundProfile,
) -> tuple[PageBackgroundProfile, dict[str, object]]:
    """Resolve the canvas authority used by final source-resolution X refinement.

    The broad page profile intentionally samples the whole perimeter.  On long
    webtoon pages edge-touching artwork can own most perimeter samples, making
    its median luminance describe artwork instead of the real page canvas.  The
    row-analysis mask already protects itself with a dominant-border colour and
    a non-dark light-page fallback.  Final X refinement must use the same rule or
    it can mistake panel artwork beyond an internal coarse boundary for canvas.
    """

    rgb, dominance, noise = _dominant_border_colour(source)
    if background.mode is not PageBackgroundMode.DARK and dominance < 0.52:
        effective_luminance = 255.0
        strategy = "legacy-light-fallback"
    else:
        effective_luminance = _rgb_luminance(rgb)
        strategy = "dominant-border"

    # Whole-perimeter spread may approach the full 0..255 range on a mixed
    # webtoon.  Dominant-bucket noise is a better estimate of actual canvas
    # variation and prevents final side tolerance from saturating on artwork.
    effective_spread = max(0.0, min(24.0, float(noise) * 2.0))
    profile = replace(
        background,
        luminance=effective_luminance,
        spread=effective_spread,
    )
    details: dict[str, object] = {
        "strategy": strategy,
        "rgb": rgb,
        "dominance": float(dominance),
        "noise": float(noise),
        "original_luminance": background.luminance,
        "original_spread": background.spread,
        "effective_luminance": profile.luminance,
        "effective_spread": profile.spread,
    }
    return profile, details


def analyze_page_v05(
    source_image: Image.Image,
    settings: FrameAnalysisSettings | None = None,
    diagnostics: DiagnosticsCollector | None = None,
) -> PageAnalysisResult:
    """Run the complete 0.5 analyzer without importing Qt or editor state."""

    if not isinstance(source_image, Image.Image):
        raise TypeError("source_image must be a PIL image")
    config = (settings or FrameAnalysisSettings()).normalized()
    captured = ListDiagnosticsCollector()
    collector: DiagnosticsCollector = (
        FanoutDiagnosticsCollector(captured, diagnostics)
        if diagnostics is not None
        else captured
    )

    transposed = ImageOps.exif_transpose(source_image)
    source = transposed.convert("RGB")
    try:
        emit(
            collector,
            "pipeline",
            "ANALYSIS_STARTED",
            "0.5 page analysis started",
            details={"width": source.width, "height": source.height},
        )
        background = analyze_background(source, collector)
        profiles, coarse_rows = detect_coarse_rows(
            source,
            background,
            config,
            collector,
        )
        refined_rows = refine_rows_at_panel_rules(
            source,
            coarse_rows,
            profiles,
            config,
            collector,
        )
        panels = split_horizontal_panels(
            source,
            refined_rows,
            background,
            config,
            collector,
        )
        side_background, side_canvas_details = resolve_side_canvas_reference(
            source,
            background,
        )
        emit(
            collector,
            "side_refine",
            "CANVAS_REFERENCE_RESOLVED",
            "resolved robust page canvas reference for final X refinement",
            details=side_canvas_details,
        )
        panels = refine_panel_sides(
            source,
            side_background,
            panels,
            config,
            collector,
        )
        frames = assemble_candidates(panels, collector)
        emit(
            collector,
            "pipeline",
            "ANALYSIS_FINISHED",
            "0.5 page analysis completed",
            details={"frames": len(frames)},
        )
        return PageAnalysisResult(
            width=source.width,
            height=source.height,
            background=background,
            frames=frames,
            diagnostics=tuple(captured.events),
            engine_api=ENGINE_API,
            engine_version=ENGINE_VERSION,
        )
    finally:
        source.close()
        if transposed is not source_image:
            transposed.close()


__all__ = ["ENGINE_API", "ENGINE_CHANGELOG", "ENGINE_VERSION", "analyze_page_v05"]
