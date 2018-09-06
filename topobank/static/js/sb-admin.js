(function($) {
  "use strict"; // Start of use strict

  // Toggle the side navigation
  $("#sidebarToggle").click(function(e) {
    e.preventDefault();
    $("body").toggleClass("sidebar-toggled");
    $(".sidebar").toggleClass("toggled");
  });

  // Prevent the content wrapper from scrolling when the fixed side navigation hovered over
  $('body.fixed-nav .sidebar').on('mousewheel DOMMouseScroll wheel', function(e) {
    if ($window.width() > 768) {
      var e0 = e.originalEvent,
        delta = e0.wheelDelta || -e0.detail;
      this.scrollTop += (delta < 0 ? 1 : -1) * 30;
      e.preventDefault();
    }
  });

  // Scroll to top button appear
  $(document).scroll(function() {
    var scrollDistance = $(this).scrollTop();
    if (scrollDistance > 100) {
      $('.scroll-to-top').fadeIn();
    } else {
      $('.scroll-to-top').fadeOut();
    }
  });

  // Smooth scrolling using jQuery easing
  $(document).on('click', 'a.scroll-to-top', function(event) {
    var $anchor = $(this);
    $('html, body').stop().animate({
      scrollTop: ($($anchor.attr('href')).offset().top)
    }, 1000, 'easeInOutExpo');
    event.preventDefault();
  });

})(jQuery); // End of use strict
$(document).ready(function() {
  "use strict"; // Start of use strict
	jQuery.expr[':'].contains = function(a, i, m) {
  return jQuery(a).text().toUpperCase()
      .indexOf(m[3].toUpperCase()) >= 0;
};
	$(".custom-search-form input[type=text]").keyup(function() {
        var valThis = $(this).val();
		$(".sidebar a").each(function() {
			if(valThis.length > 0) {
					$(this).hide();
				if ($(this).parent('.dropdown-menu').length !== 0) {
					$(this).parent('.dropdown-menu').removeClass("show").hide();
					$(this).parent('.dropdown-menu').parent().find('.dropdown-toggle').removeClass("show").hide();
					$(this).parents('.dropdown-menu').closest('li.dropdown').removeClass("show").hide();
					//console.log($(this).parents('.dropdown-menu').closest('li.dropdown').html());
				}
			} else if(valThis.length < 1) {
				$(this).show();
			}
		});
	   $(".sidebar a:contains('" + valThis + "')").each(function() {
			if(valThis.length > 0) {
				$( this ).show();
				if ($(this).parent('.dropdown-menu').length !== 0) {
					$(this).parent('.dropdown-menu').addClass("show").show();
					$(this).parent('.dropdown-menu').parent().find('.dropdown-toggle').addClass("show").show();
					$(this).parents('.dropdown-menu').closest('li.dropdown').addClass("show").show();
				}
			}
		});
    });
});
