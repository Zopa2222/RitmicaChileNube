from io import BytesIO
from pathlib import Path

import openpyxl
import pytest

from app.services.cloud_excel_service import (
    ExcelImportError,
    analyze_excel,
    build_sheet_plan,
    render_preview,
    validate_cutoff_decisions,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def workbook_bytes(marker='ALMUERZO JUECES'):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = 'SABADO'
    sheet.append([
        'N', 'NOMBRE', 'CLUB', 'CATEGORIA',
        'N', 'NOMBRE', 'CLUB', 'CATEGORIA',
    ])
    sheet.append([
        1, 'Gimnasta A1', 'Club A', 'MINI A',
        1, 'Gimnasta B1', 'Club B', 'MINI B',
    ])
    sheet.append([
        2, 'Gimnasta A2', 'Club A', 'MINI A',
        2, 'Gimnasta B2', 'Club B', 'MINI B',
    ])
    sheet.append([marker, None, None, None, None, None, None, None])
    sheet.append([
        'N', 'NOMBRE', 'CLUB', 'CATEGORIA',
        'N', 'NOMBRE', 'CLUB', 'CATEGORIA',
    ])
    sheet.append([
        1, 'Gimnasta A3', 'Club A', 'JUNIOR A',
        1, 'Gimnasta B3', 'Club B', 'JUNIOR B',
    ])
    output = BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def test_real_centro_excel_detects_validated_cut_and_banks():
    analysis = analyze_excel((PROJECT_ROOT / 'CENTRO.xlsx').read_bytes())
    preview = render_preview(analysis)
    sheet = preview['sheets'][0]

    assert sheet['name'] == 'SABADO'
    assert sheet['detected_cutoff_row'] == 92
    assert preview['total_categories'] == 52
    assert preview['total_gymnasts'] == 295
    assert sheet['summary']['A']['AM'] == {
        'categories': 6,
        'gymnasts': 84,
    }
    assert sheet['summary']['B']['PM'] == {
        'categories': 22,
        'gymnasts': 65,
    }
    markers = {marker['row']: marker for marker in sheet['markers']}
    assert markers[92]['primary_candidate']
    assert not markers[147]['primary_candidate']
    assert not markers[168]['eligible_cutoff']


def test_short_break_requires_manual_cut_decision():
    analysis = analyze_excel(workbook_bytes('BREAK 15 MINUTOS'))
    preview = render_preview(analysis)

    assert preview['sheets'][0]['detected_cutoff_row'] is None
    assert preview['sheets'][0]['requires_manual_decision']

    decisions = validate_cutoff_decisions(
        analysis,
        [{'sequence': 1, 'cutoff_row': 4, 'confirmed': True}],
    )
    updated = render_preview(analysis, decisions)
    assert updated['sheets'][0]['selected_cutoff_row'] == 4
    assert updated['sheets'][0]['cutoff_confirmed']


def test_cutoff_cannot_split_same_category():
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(['N', 'NOMBRE', 'CLUB', 'CATEGORIA'])
    sheet.append([1, 'Primera', 'Club', 'MISMA'])
    sheet.append(['ALMUERZO JUECES'])
    sheet.append(['N', 'NOMBRE', 'CLUB', 'CATEGORIA'])
    sheet.append([2, 'Segunda', 'Club', 'MISMA'])
    output = BytesIO()
    workbook.save(output)
    workbook.close()

    analysis = analyze_excel(output.getvalue())

    with pytest.raises(ExcelImportError):
        build_sheet_plan(analysis['sheets'][0], 3)
