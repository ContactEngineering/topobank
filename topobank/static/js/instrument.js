/**
 * Definitions for UI, related to reliability analysis:
 * */

function add_asterisks_to_all_labels(div_elem) {
    div_elem.find('label').append('<span class="asteriskField">*</span>');
}

function remove_asterisks_from_all_labels(div_elem) {
    div_elem.find('span[class="asteriskField"]').remove();
}


/**
 * Set some labels based on instrument type setting
 */
function update_instrument_parameters_in_form(instrument_parameters) {

    let instrument_type = $('#id_instrument_type').val();
    let div_instrument_resolution = $('div.instrument-resolution');
    let div_instrument_tip_radius = $('div.instrument-tip-radius');

    if (instrument_parameters === undefined) {
        instrument_parameters = {};
    }

    console.log(`Updating instrument parameters for instrument type ${instrument_type}..`);
    console.log(instrument_parameters);

    if (instrument_type === 'microscope-based') {
            if (instrument_parameters.hasOwnProperty('resolution')) {
                $("#id_resolution_value").val(instrument_parameters.resolution.value);
                $("#id_resolution_unit").val(instrument_parameters.resolution.unit);
            }

            add_asterisks_to_all_labels(div_instrument_resolution);
            div_instrument_resolution.show();
            remove_asterisks_from_all_labels(div_instrument_tip_radius);
            div_instrument_tip_radius.hide();
    } else if (instrument_type === 'contact-based') {
            if (instrument_parameters.hasOwnProperty('tip_radius')) {
                $("#id_tip_radius_value").val(instrument_parameters.tip_radius.value);
                $("#id_tip_radius_unit").val(instrument_parameters.tip_radius.unit);
            }
            remove_asterisks_from_all_labels(div_instrument_resolution);
            div_instrument_resolution.hide();
            add_asterisks_to_all_labels(div_instrument_tip_radius);
            div_instrument_tip_radius.show();
    } else {
        remove_asterisks_from_all_labels(div_instrument_resolution);
        remove_asterisks_from_all_labels(div_instrument_tip_radius);
        div_instrument_resolution.hide();
        div_instrument_tip_radius.hide();
    }
}
