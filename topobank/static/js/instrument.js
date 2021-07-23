/**
 * Definitions for UI, related to reliability analysis:
 * */

const instrument_id_placeholder = '999999999';  // this is used in an URL as placeholder, see below

/**
 *
 * @param instrument_json_url_template  url in which the placeholder defined above can be replaced
 *                                      by the real instrument_id
 */
function update_instrument_parameters(instrument_json_url_template) {

    let instrument_id = $('#id_instrument').val();

    let instrument_json_url = instrument_json_url_template.replace(instrument_id_placeholder, instrument_id);

    console.log("Instrument JSON URL:" + instrument_json_url);
    console.log("instrument_id:" + instrument_id);

    if ((instrument_id === undefined) || (instrument_id === "")) {
        set_reliability_input_labels({}, false);
    } else {
        $.ajax({
            url: instrument_json_url,
            type: 'get',
            success: function (data) {
                console.log("Instrument parameters received: " + data);
                set_reliability_input_labels(JSON.parse(data));
            },
            error: function (xhr, textStatus, errorThrown) {
                /**
                 * If an error occurs *not* because of XMLHttpRequest.abort(), show an
                 * error message. Do not show error on .abort(). See also
                 * https://developer.mozilla.org/en-US/docs/Web/API/XMLHttpRequest/abort
                 * */
                if (xhr.status == 0) {
                    console.log("Canceled instrument retrieval.");
                    $('#instrument-retrieval-message').html('Canceled loading of instrument parameters.')
                } else {
                    console.error("Could not retrieve instrument parameters: " + errorThrown + " "
                        + xhr.status + " " + xhr.responseText);
                    $('#instrument-retrieval-message').html(`
                      <div class='alert alert-danger'>
                          Could not request instrument info. Error: ${errorThrown}
                      </div>`);
                }
            }
        });
    }

}

/**
 * @param instrument_data
 */
function set_reliability_input_labels(instrument_data) {
    let instrument_details_defined = (instrument_data.type !== undefined);
    // undefined if the data is empty
    //
    // There is another case: 'undefined' if it's an instrument with type 'undefined', see below

    let instrument_parameters_available = (instrument_data.parameters !== undefined)
                                                && (!$.isEmptyObject(instrument_data.parameters));

    let reliability_factor_name = undefined;
    let reliability_factor_value = undefined;
    let reliability_factor_unit = undefined;
    let instrument_details = $('.instrument-detail');  // name, description, type (fixed for all measurements)
    let instrument_parameters = $('.instrument-parameters');
    // resolution, tip_radius, ... (can vary between measurements)

    if (instrument_details_defined) {

        // Replace "reliability_factor" items based on type setting
        let selected_type = instrument_data.type;
        let params = instrument_data.parameters;
        console.log("Setting instrument details..");

        $('#id_instrument_name').text(instrument_data.name);
        $('#id_instrument_type').text(selected_type);
        $('#id_instrument_description').text(instrument_data.description);

        instrument_details.show();

        if (instrument_parameters_available) {

            console.log("Setting instrument parameters..");

            reliability_factor_value = '';
            reliability_factor_unit = '';

            if (selected_type === 'microscope-based') {
                reliability_factor_name = "Resolution";
                if (params.hasOwnProperty('resolution')) {
                    reliability_factor_value = params.resolution.value;
                    reliability_factor_unit = params.resolution.unit;
                }
            } else if (selected_type === 'contact-based') {
                reliability_factor_name = "Tip radius";
                if (params.hasOwnProperty('tip_radius')) {
                    reliability_factor_value = params.tip_radius.value;
                    reliability_factor_unit = params.tip_radius.unit;
                }
            }

            $("label[for='id_reliability_factor_value']").text(reliability_factor_name);
            $("#id_reliability_factor_value").val(reliability_factor_value);
            $("label[for='id_reliability_factor_unit']").text(reliability_factor_name + ' unit');
            $("#id_reliability_factor_unit").val(reliability_factor_unit);

            instrument_parameters.show();
        } else {
            console.log("No instrument parameters given.");
            instrument_parameters.hide();
        }
    } else {
        console.log("No instrument details known.");
        // remove UI elements from form
        instrument_details.hide();
        instrument_parameters.hide();
    }
}
