"""墨区着墨面积（ink-zones）算法单元测试。"""
import pytest

from app.imposition import ink_zone_coverage


def _rect(x, y, w, h, c=0.0, m=0.0, yk=0.0, k=0.0):
    return {
        "x_mm": x, "y_mm": y, "width_mm": w, "height_mm": h,
        "cyan": c, "magenta": m, "yellow": yk, "key": k,
    }


def _ink(pages, *, zones=4, run=1, **overrides):
    """默认 4 页 1 张、左装订、页宽 200、页高 100、无中缝、long 翻转。"""
    params = {
        "total_pages": 4,
        "max_sheets": 1,
        "binding": "left",
        "page_width_mm": 200.0,
        "page_height_mm": 100.0,
        "gutter_mm": 0.0,
        "duplex_flip": "long",
        "ink_zone_count": zones,
        "print_run": run,
        "pages": pages,
    }
    params.update(overrides)
    return ink_zone_coverage(**params)


def _channel(zone, name):
    return zone[f"{name}_area_mm2"]


def _side_channels(sheet, side):
    return [
        tuple(_channel(z, c) for c in ("cyan", "magenta", "yellow", "key"))
        for z in sheet[side]["zones"]
    ]


def test_paper_and_zone_geometry():
    result = _ink([], zones=4, gutter_mm=40.0)
    # 纸面宽 = 2 × 200 + 40 = 440；墨区等宽 110
    assert result["paper_width_mm"] == 440.0
    assert result["paper_height_mm"] == 100.0
    assert result["zone_width_mm"] == 110.0
    zones = result["signatures"][0]["sheets"][0]["front"]["zones"]
    assert [(z["zone_index"], z["x_mm"], z["width_mm"]) for z in zones] == [
        (1, 0.0, 110.0),
        (2, 110.0, 110.0),
        (3, 220.0, 110.0),
        (4, 330.0, 110.0),
    ]


def test_front_right_slot_zero_rotation_maps_directly():
    # 左装订正面右槽 = 第 1 页（x=200），旋转 0
    result = _ink(
        [{"page": 1, "rectangles": [_rect(0, 0, 150, 10, c=0.5)]}],
        zones=4,
    )
    sheet = result["signatures"][0]["sheets"][0]
    # 纸面矩形 [200, 350]：墨区 3 [200,300) 交 100mm、墨区 4 [300,400) 交 50mm；
    # 面积 100×10×0.5=500、50×10×0.5=250
    assert _side_channels(sheet, "front") == [
        (0.0, 0.0, 0.0, 0.0),
        (0.0, 0.0, 0.0, 0.0),
        (500.0, 0.0, 0.0, 0.0),
        (250.0, 0.0, 0.0, 0.0),
    ]
    # 第 1 页在正面，背面全无着墨
    assert _side_channels(sheet, "back") == [(0.0, 0.0, 0.0, 0.0)] * 4


def test_long_flip_back_uses_swapped_slot():
    # long 背面右槽 = 第 2 页（x=200），旋转 0
    result = _ink(
        [{"page": 2, "rectangles": [_rect(50, 0, 50, 10, m=0.2)]}],
        zones=4,
    )
    sheet = result["signatures"][0]["sheets"][0]
    # 纸面 [250, 300] 全在墨区 3：面积 50×10×0.2 = 100
    assert _side_channels(sheet, "back")[2] == (0.0, 100.0, 0.0, 0.0)
    assert _side_channels(sheet, "front") == [(0.0, 0.0, 0.0, 0.0)] * 4


def test_short_flip_back_rotates_rect_180():
    # short 背面左槽 = 第 2 页（x=0），旋转 180
    result = _ink(
        [{"page": 2, "rectangles": [_rect(50, 0, 50, 10, yk=0.4)]}],
        zones=4, duplex_flip="short",
    )
    sheet = result["signatures"][0]["sheets"][0]
    # 180° 映射：paper x = 200 − 50 − 50 = 100，[100,150] 全在墨区 2
    back = _side_channels(sheet, "back")
    assert back[1] == (0.0, 0.0, 200.0, 0.0)  # 50×10×0.4
    assert back[0] == back[2] == back[3] == (0.0, 0.0, 0.0, 0.0)
    # y 也旋转：paper y = 100 − 0 − 10 = 90；条高 100 内整段仍同高，面积不变


def test_short_flip_y_axis_flips():
    # 非整高矩形验证 y 旋转：宽 100、高 20，页内 y=30 -> 纸面 y=100-30-20=50
    result = _ink(
        [{"page": 2, "rectangles": [_rect(0, 30, 100, 20, k=1.0)]}],
        zones=2, duplex_flip="short",
    )
    sheet = result["signatures"][0]["sheets"][0]
    # paper [0,100]×[50,70]：墨区 1 面积 100×20 = 2000
    assert _side_channels(sheet, "back")[0] == (0.0, 0.0, 0.0, 2000.0)


def test_rect_straddling_zone_boundary_split_by_overlap():
    # 墨区宽 100；页内 x=80、宽 40 -> 纸面右槽 [280,320]
    result = _ink(
        [{"page": 1, "rectangles": [_rect(80, 0, 40, 30, c=1.0)]}],
        zones=4,
    )
    front = _side_channels(
        result["signatures"][0]["sheets"][0], "front"
    )
    # 墨区 3 [200,300) 交 20mm -> 600；墨区 4 [300,400) 交 20mm -> 600
    assert front[2] == (600.0, 0.0, 0.0, 0.0)
    assert front[3] == (600.0, 0.0, 0.0, 0.0)


def test_gutter_receives_no_ink():
    # 中缝 40：右槽 x=240；整页矩形 200 宽 -> 纸面 [240,440]，墨区宽 110
    result = _ink(
        [{"page": 1, "rectangles": [_rect(0, 0, 200, 100, c=1.0)]}],
        zones=4, gutter_mm=40.0,
    )
    front = _side_channels(
        result["signatures"][0]["sheets"][0], "front"
    )
    # 区3 [220,330) 交 90mm=9000；区4 [330,440] 交 110mm=11000；区1/2 为 0
    assert front[0][0] == 0.0
    assert front[1][0] == 0.0
    assert front[2][0] == pytest.approx(9000.0)
    assert front[3][0] == pytest.approx(11000.0)


def test_multiple_rectangles_accumulate_in_same_zone():
    result = _ink(
        [{"page": 1, "rectangles": [
            _rect(0, 0, 50, 10, c=1.0),
            _rect(60, 0, 20, 10, c=0.5),
        ]}],
        zones=4,
    )
    front = _side_channels(
        result["signatures"][0]["sheets"][0], "front"
    )
    # 两个矩形都在纸面墨区 3（右槽 [200,250] 与 [260,280]）：
    # 50×10×1 + 20×10×0.5 = 600
    assert front[2] == (600.0, 0.0, 0.0, 0.0)


def test_rectangle_on_page_edge_is_clamped_not_invalid():
    # 浮点噪声使矩形恰好贴在页面边缘
    result = _ink(
        [{"page": 1, "rectangles": [
            _rect(0.0, 0.0, 200.00000000001, 100.0, c=1.0)]}],
        zones=2,
    )
    front = _side_channels(
        result["signatures"][0]["sheets"][0], "front"
    )
    # 整页在右槽：墨区 2 整页面积 20000
    assert front[1] == (20000.0, 0.0, 0.0, 0.0)


def test_print_run_multiplies_all_channels():
    result = _ink(
        [{"page": 1, "rectangles": [
            _rect(0, 0, 100, 10, c=0.1, m=0.2, yk=0.3, k=0.4)]}],
        zones=4, run=7,
    )
    front = _side_channels(
        result["signatures"][0]["sheets"][0], "front"
    )
    # 纸面右槽 [200,300] 全在墨区 3：基础 100×10=1000，分别乘覆盖率与印数 7
    assert front[2] == (700.0, 1400.0, 2100.0, 2800.0)


def test_single_zone_covers_whole_paper():
    result = _ink(
        [{"page": 1, "rectangles": [_rect(0, 0, 200, 100, k=0.5)]}],
        zones=1,
    )
    zones = result["signatures"][0]["sheets"][0]["front"]["zones"]
    assert len(zones) == 1
    assert zones[0]["x_mm"] == 0.0
    assert zones[0]["width_mm"] == 400.0
    assert zones[0]["key_area_mm2"] == pytest.approx(10000.0)  # 200×100×0.5


def test_sixteen_zones():
    result = _ink([], zones=16)
    zones = result["signatures"][0]["sheets"][0]["front"]["zones"]
    assert len(zones) == 16
    assert zones[0]["width_mm"] == 25.0
    assert zones[-1]["zone_index"] == 16
    assert zones[-1]["x_mm"] == 375.0


def test_blank_pages_not_counted():
    # 1 页补 3 空白：正面 (空白, 1)、背面全空白
    result = _ink(
        [{"page": 1, "rectangles": [_rect(0, 0, 200, 100, c=1.0)]}],
        zones=2, total_pages=1,
    )
    sheet = result["signatures"][0]["sheets"][0]
    assert _side_channels(sheet, "back") == [(0.0, 0.0, 0.0, 0.0)] * 2
    # 正面仅右槽墨区 2 有墨
    assert _side_channels(sheet, "front")[0] == (0.0, 0.0, 0.0, 0.0)
    assert _side_channels(sheet, "front")[1][0] == 20000.0


def test_multi_signature_pages_distributed():
    result = _ink(
        [{"page": p, "rectangles": [_rect(0, 0, 10, 10, k=1.0)]}
         for p in range(1, 7)],
        zones=2, total_pages=6, max_sheets=1,
    )
    assert result["signature_count"] == 2
    assert result["signatures"][1]["page_count_padded"] == 4
    # 帖 2 正面右槽 = 第 5 页（x=200），矩形在纸面 [200,210]、墨区 2 [200,400]
    sheet2 = result["signatures"][1]["sheets"][0]
    assert _side_channels(sheet2, "front")[1][3] == 100.0


def test_right_binding_mirror_page_order():
    # 右装订正面：左槽 = 第 1 页、右槽 = 第 4 页
    result = _ink(
        [{"page": 1, "rectangles": [_rect(0, 0, 50, 10, c=1.0)]}],
        zones=4, binding="right",
    )
    front = _side_channels(
        result["signatures"][0]["sheets"][0], "front"
    )
    # 第 1 页在左槽 [0,50]：墨区 1
    assert front[0] == (500.0, 0.0, 0.0, 0.0)


def test_empty_page_rectangles_and_missing_pages_contribute_nothing():
    result = _ink(
        [{"page": 1, "rectangles": []},
         {"page": 2, "rectangles": []}],
        zones=3,
    )
    for sheet_side in ("front", "back"):
        for zone in result["signatures"][0]["sheets"][0][sheet_side]["zones"]:
            assert all(
                zone[f"{c}_area_mm2"] == 0.0
                for c in ("cyan", "magenta", "yellow", "key")
            )


# ---------------------------------------------------------------------------
# 参数校验
# ---------------------------------------------------------------------------


def test_invalid_page_number_raises():
    with pytest.raises(ValueError):
        _ink([{"page": 0, "rectangles": [_rect(0, 0, 10, 10)]}])
    with pytest.raises(ValueError):
        _ink([{"page": 5, "rectangles": [_rect(0, 0, 10, 10)]}])


def test_duplicate_page_entry_raises():
    with pytest.raises(ValueError):
        _ink([
            {"page": 1, "rectangles": [_rect(0, 0, 10, 10)]},
            {"page": 1, "rectangles": [_rect(20, 20, 10, 10)]},
        ])


def test_rectangle_out_of_page_raises():
    bad_rects = [
        _rect(-1, 0, 10, 10),       # x 为负
        _rect(0, -1, 10, 10),       # y 为负
        _rect(195, 0, 10, 10),      # 右边越界
        _rect(0, 95, 10, 10),       # 底边越界
        _rect(0, 0, 0, 10),         # 宽为 0
        _rect(0, 0, 10, -5),        # 高为负
    ]
    for rect in bad_rects:
        with pytest.raises(ValueError):
            _ink([{"page": 1, "rectangles": [rect]}])


def test_non_finite_rectangle_values_raise():
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            _ink([{"page": 1, "rectangles": [
                _rect(value, 0, 10, 10)]}])
        with pytest.raises(ValueError):
            _ink([{"page": 1, "rectangles": [
                _rect(0, 0, value, 10)]}])


def test_coverage_out_of_range_raises():
    for channel in ("cyan", "magenta", "yellow", "key"):
        for value in (-0.01, 1.01):
            rect = _rect(0, 0, 10, 10)
            rect[channel] = value
            with pytest.raises(ValueError):
                _ink([{"page": 1, "rectangles": [rect]}])


def test_overlapping_rectangles_on_same_page_raise():
    with pytest.raises(ValueError):
        _ink([{"page": 1, "rectangles": [
            _rect(0, 0, 10, 10),
            _rect(5, 5, 10, 10),
        ]}])
    # 仅边缘相切不算重叠
    _ink([{"page": 1, "rectangles": [
        _rect(0, 0, 10, 10),
        _rect(10, 0, 10, 10),
    ]}])
    # 不同页的同坐标矩形不冲突
    _ink([
        {"page": 1, "rectangles": [_rect(0, 0, 10, 10)]},
        {"page": 2, "rectangles": [_rect(0, 0, 10, 10)]},
    ])


def test_zone_count_and_print_run_bounds():
    for count in (0, 17, -1):
        with pytest.raises(ValueError):
            _ink([], zones=count)
    for run in (0, -3):
        with pytest.raises(ValueError):
            _ink([], run=run)
