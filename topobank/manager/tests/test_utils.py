"""
Tests for the interface to topography files
and other things in topobank.manager.utils
"""

from pathlib import Path

from ..utils import TopographyFile, DEFAULT_DATASOURCE_NAME

def test_data_sources_txt():

    input_file_path = Path('topobank/manager/fixtures/example4.txt')  # TODO use standardized way to find files

    topofile = TopographyFile(input_file_path)

    assert topofile.data_sources == [DEFAULT_DATASOURCE_NAME]



