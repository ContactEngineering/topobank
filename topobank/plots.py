from bokeh.models.formatters import FuncTickFormatter

def configure_plot(plot):
    plot.toolbar.logo = None
    plot.xaxis.axis_label_text_font_style = "normal"
    plot.yaxis.axis_label_text_font_style = "normal"
    plot.xaxis.major_label_text_font_size = "1rem"
    plot.yaxis.major_label_text_font_size = "1rem"
    plot.xaxis.axis_label_text_font_size = "1rem"
    plot.yaxis.axis_label_text_font_size = "1rem"
    plot.xaxis.formatter = FuncTickFormatter(code="return format_exponential(tick);")
    plot.yaxis.formatter = FuncTickFormatter(code="return format_exponential(tick);")
