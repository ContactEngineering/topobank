/*
 * Convert numerals inside a string into the unicode superscript equivalent, e.g.
 *   µm3 => µm³
 */
function unicodeSuperscript(s) {
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
export function formatExponential(d, maxNumberOfDecimalPlaces) {
  if (maxNumberOfDecimalPlaces === undefined) {
    maxNumberOfDecimalPlaces = 3;
  }

  if (d === 0 || d === undefined || isNaN(d) || Math.abs(d) == Infinity) {
    return String(d);
  } else if ("number" === typeof d) {
    const multiplier = Math.pow(10, maxNumberOfDecimalPlaces);
    const sign = d < 0 ? -1 : 1;
    let e = Math.floor(Math.log(sign * d) / Math.log(10));
    const m = sign * d / Math.pow(10, e);
    let m_rounded = Math.round(m * multiplier) / multiplier;
    if (10 === m_rounded) {
      m_rounded = 1;
      e++;
    }
    if (0 === e) {
      return String(sign * m_rounded); // do not attach ×10⁰ == 1
    } else if (1 == m_rounded) {
      if (0 < sign) {
        return "10" + unicodeSuperscript(String(e));
      } else {
        return "-10" + unicodeSuperscript(String(e));
      }
    } else {
      return String(sign * m_rounded) + "×10" + unicodeSuperscript(String(e));
    }
  } else {
    return String(d);
  }
}
