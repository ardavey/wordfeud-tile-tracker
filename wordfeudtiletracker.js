(function(d, s, id) {
  var js, fjs = d.getElementsByTagName(s)[0];
  if (d.getElementById(id)) return;
  js = d.createElement(s); js.id = id;
  js.src = "//connect.facebook.net/en_GB/all.js#xfbml=1";
  fjs.parentNode.insertBefore(js, fjs);
}(document, 'script', 'facebook-jssdk'));

$( document ).ready( function() {
  $( "div.togglable" ).hide();
  
  $( "#yourtoggle" ).click( function() {
    $( "#yourturnsection" ).slideToggle();
  });
  
  $( "#theirtoggle" ).click( function() {
    $( "#theirturnsection" ).slideToggle();
  });

  $( "#completedtoggle" ).click( function() {
    $( "#completedsection" ).slideToggle();
  });

  $( "#archivetoggle" ).click( function() {
    $( "#archivesection" ).slideToggle();
  });
});
