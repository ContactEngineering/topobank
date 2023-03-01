/* Project specific Javascript goes here. */
"use strict";
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

/*
 * Convert numerals inside a string into the unicode superscript equivalent, e.g.
 *   µm3 => µm³
 */
function unicode_superscript(s) {
    var superscript_dict = {
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

        if (d === 0 || d === undefined || isNaN(d) || Math.abs(d) == Infinity) {
            return String(d);
        }
        else if ("number" === typeof d) {
            var multiplier = Math.pow(10, maxNumberOfDecimalPlaces);
            var sign = d < 0 ? -1 : 1;
            var e = Math.floor(Math.log(sign * d) / Math.log(10));
            var m = sign * d / Math.pow(10, e);
            var m_rounded = Math.round(m * multiplier) / multiplier;
            if (10 == m_rounded) {
                m_rounded = 1;
                e++;
            }
            if (0 == e) {
                return String(sign * m_rounded); // do not attach ×10⁰ == 1
            }
            else if (1 == m_rounded) {
                if (0 < sign) {
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
