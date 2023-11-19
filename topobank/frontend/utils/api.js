export function subjectsToBase64(subjects) {
    return btoa(JSON.stringify(subjects));
}

export function getIdFromUrl(url) {
    const s = url.split('/');
    return Number(s[s.length - 2]);
}


export function filterTopographyForPatchRequest(topography) {
    // Copy writable entries
    let writeableEntries = [
        'description', 'instrument_name', 'instrument_parameters', 'instrument_type', 'measurement_date', 'name',
        'tags', 'detrend_mode', 'fill_undefined_data_mode', 'data_source'
    ];
    if (topography.size_editable) {
        writeableEntries.push('size_x', 'size_y');
    }
    if (topography.unit_editable) {
        writeableEntries.push('unit');
    }
    if (topography.height_scale_editable) {
        writeableEntries.push('height_scale');
    }
    if (topography.is_periodic_editable) {
        writeableEntries.push('is_periodic');
    }

    let returnDict = {};
    for (const e of writeableEntries) {
        if (topography[e] != null) {
            returnDict[e] = topography[e];
        }
    }

    // Uncomment to simulate error on PATCH
    // returnDict['thumbnail'] = 'def';

    return returnDict;
}
