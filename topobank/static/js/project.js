/* Project specific Javascript goes here. */

/*
Formatting hack to get around crispy-forms unfortunate hardcoding
in helpers.FormHelper:

    if template_pack == 'bootstrap4':
        grid_colum_matcher = re.compile('\w*col-(xs|sm|md|lg|xl)-\d+\w*')
        using_grid_layout = (grid_colum_matcher.match(self.label_class) or
                             grid_colum_matcher.match(self.field_class))
        if using_grid_layout:
            items['using_grid_layout'] = True

Issues with the above approach:

1. Fragile: Assumes Bootstrap 4's API doesn't change (it does)
2. Unforgiving: Doesn't allow for any variation in template design
3. Really Unforgiving: No way to override this behavior
4. Undocumented: No mention in the documentation, or it's too hard for me to find
*/
$('.form-group').removeClass('row');

function siSuffixMeters(numberOfSignificantFigures = 3) {
  return d => d3.format("." + numberOfSignificantFigures + "s")(d)+ "m";
}

/*
 * Convert numerals inside a string into the unicode superscript equivalent, e.g.
 *   µm3 => µm³
 */
function unicode_superscript(s) {
    superscript_dict = {
        '0': '⁰',
        '1': '¹',
        '2': '²',
        '3': '³',
        '4': '⁴',
        '5': '⁵',
        '6': '⁶',
        '7': '⁷',
        '8': '⁸',
        '9': '⁹',
        '+': '⁺',
        '-': '⁻',
        '.': '⋅',
    };
    return s.split('').map(c => c in superscript_dict ? superscript_dict[c] : c).join('');
}


/**
 * Creates a formatter that formats numbers to show no more than
 * [maxNumberOfDecimalPlaces] decimal places in exponential notation.
 * Exponentials will be displayed human readably, i.e. 1.3×10³.
 *
 * @param {number} [d] The number to be formatted
 * @param {number} [maxNumberOfDecimalPlaces] The number of decimal places to show (default 3).
 *
 * @returns {Formatter} A formatter for general values.
 */
function format_exponential(d, maxNumberOfDecimalPlaces) {
        if (maxNumberOfDecimalPlaces === void 0) { maxNumberOfDecimalPlaces = 3; }

        if (d == 0 || d === undefined || isNaN(d) || Math.abs(d) == Infinity) {
            return String(d);
        }
        else if (typeof d === "number") {
            var multiplier = Math.pow(10, maxNumberOfDecimalPlaces);
            var sign = d < 0 ? -1 : 1;
            var e = Math.floor(Math.log(sign * d) / Math.log(10));
            var m = sign * d / Math.pow(10, e);
            var m_rounded = Math.round(m * multiplier) / multiplier;
            if (m_rounded == 10) {
                m_rounded = 1;
                e++;
            }
            if (e == 0) {
                return String(sign * m_rounded); // do not attach ×10⁰ == 1
            }
            else if (m_rounded == 1) {
                if (sign > 0) {
                    return "10" + unicode_superscript(String(e));
                }
                else {
                    return "-10" + unicode_superscript(String(e));
                }
            }
            else {
                return String(sign * m_rounded) + "×10" + unicode_superscript(String(e));
            }
        }
        else {
            return String(d);
        }
}

/**
 * Submit an ajax call for updating an card in the analysis view.
 *
 * @param card_url {String} URL to call in order to get card content as HTTP response
 * @param card_element_id {String} CSS id of the div element containing the card
 * @param template_flavor {String} defines which template should be finally used (e.g. 'list', 'detail')
 * @param function_id {Number} Integer number of the analysis function which should be displayed
 * @param topography_ids {Object} list of integer numbers with ids of topographies which should be displayed
 * @param call_count {Integer} 0 for first call in a chain of ajax calls, increased by one in further calls
 */
function submit_analyses_card_ajax(card_url, card_element_id, template_flavor, function_id, topography_ids, call_count) {

      var jquery_card_selector = "#"+card_element_id;
      var jquery_indicator_selector = jquery_card_selector+"-wait-text"; // for increasing number of dots after each ajax call
      // see GH 236

      if (call_count === undefined) {
          call_count = 0; // first call
      }

      // Provide effect of growing list of dots as long as background task is not finished (see #236)
      var dots = '.'.repeat((call_count % 9)+1);
      $(jquery_indicator_selector).text('Please wait'+dots);

      $.ajax({
        type: "POST",
        url: card_url,
        timeout: 0,
        data: {
           card_id: card_element_id,
           template_flavor: template_flavor,
           function_id: function_id,
           topography_ids: topography_ids,
           csrfmiddlewaretoken: csrf_token
        },
        success : function(data, textStatus, xhr) {

          if ((call_count == 0) || (xhr.status==200) ) {
            $(jquery_card_selector).html(data); // insert resulting HTML code
            // We want to only insert cards on first and last call and
            // only once if there is only one call.
          }
          if (xhr.status==202) {
            // Not all analyses are ready, retrigger AJAX call
            console.log("Analyses for card with element id '"+card_element_id+"' not ready. Retrying..");
            setTimeout(function () {
              submit_analyses_card_ajax(card_url, card_element_id, template_flavor, function_id, topography_ids, call_count+1);
            }, 1000); // TODO limit number of retries?
          }
        },
        error: function(xhr, textStatus, errorThrown) {
          // console.log("Error receiving response for card '"+card_element_id+"'. Status: "+xhr.status
          //            +" Response: "+xhr.responseText)
          if (errorThrown != "abort") {
              $(jquery_card_selector).html("Please report this error: " + errorThrown + " " + xhr.status + " " + xhr.responseText);
              $(jquery_card_selector).addClass("alert alert-danger");
          }
        }
      });
}

/**
 * Submit an ajax call for updating an card in the surfaces view.
 *
 * @param card_url {String} URL to call in order to get card content as HTTP response
 * @param surface_id {Number} Id of the surface being displayed
 * @param parent_path {String} URL which can be used to provide a target on pressing cancel button
 */
function submit_surface_card_ajax(card_url, surface_id, parent_path) {

      var jquery_card_selector = "#card-"+surface_id;

      // console.log("Submitting AJAX call for surface card "+jquery_card_selector+"..");

      $.ajax({
        type: "GET",
        url: card_url,
        timeout: 0,
        data: {
           surface_id: surface_id,
           parent_path: parent_path
        },
        success : function(data, textStatus, xhr) {
            // console.log("Received response for card '" + jquery_card_selector + "'. Status: " + xhr.status);
            $(jquery_card_selector).html(data); // insert resulting HTML code
            if (xhr.status == 202) {
                // Data is not ready, retrigger AJAX call
                setTimeout(function () {
                    submit_surface_card_ajax(card_url, surface_id);
                }, 1000);
            }
        },
        error: function(xhr, textStatus, errorThrown) {
          // console.log("Error receiving response for card '"+card_element_id+"'. Status: "+xhr.status
          //            +" Response: "+xhr.responseText)
          if (errorThrown != "abort") {
              $(jquery_card_selector).html("Please report this error: " + errorThrown + " " + xhr.status + " " +xhr.responseText);
              $(jquery_card_selector).addClass("alert alert-danger");
          }
        }
      });
}

/*
 * Install a handler which aborts all running AJAX calls when leaving the page
 */
function install_handler_for_aborting_all_ajax_calls_on_page_leave() {

    // taken from https://stackoverflow.com/a/10701856/10608001, thanks grr, kzfabi on Stackoverflow!

    // Automatically cancel unfinished ajax requests
    // when the user navigates elsewhere.
    (function($) {
      var xhrPool = [];
      $(document).ajaxSend(function(e, jqXHR, options){
        xhrPool.push(jqXHR);
        // console.log("Added AJAX to pool. Now "+xhrPool.length+" AJAX calls in pool.");
      });
      $(document).ajaxComplete(function(e, jqXHR, options) {
        xhrPool = $.grep(xhrPool, function(x){return x!=jqXHR});
        // console.log("Removed AJAX from pool. Now "+xhrPool.length+" AJAX calls in pool.");
      });
      var abort_all_ajax_calls = function() {
        // console.log("Aborting all "+xhrPool.length+" AJAX calls..");
        $.each(xhrPool, function(idx, jqXHR) {
          jqXHR.abort();
        });
      };

      var oldbeforeunload = window.onbeforeunload;
      window.onbeforeunload = function() {
        var r = oldbeforeunload ? oldbeforeunload() : undefined;
        if (r == undefined) {
          // only cancel requests if there is no prompt to stay on the page
          // if there is a prompt, it will likely give the requests enough time to finish
          abort_all_ajax_calls();
        }
        return r;
      }
    })(jQuery);

}



/*
 * Setup document handlers.
 */
$(document).ready(function ($) {
    $('.clickable-table-row').click(function () {
        window.document.location = $(this).data("href");
    });
});
