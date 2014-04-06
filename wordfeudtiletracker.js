(function(d, s, id) {
  var js, fjs = d.getElementsByTagName(s)[0];
  if (d.getElementById(id)) return;
  js = d.createElement(s); js.id = id;
  js.src = "//connect.facebook.net/en_GB/all.js#xfbml=1";
  fjs.parentNode.insertBefore(js, fjs);
}(document, 'script', 'facebook-jssdk'));

$( document ).ready( function() {
  $( ".togglable" ).hide();
  
  $( "#yourtoggle" ).click( function() {
    $( "#yourturnsection" ).slideToggle( "fast" );
  });
  
  $( "#theirtoggle" ).click( function() {
    $( "#theirturnsection" ).slideToggle( "fast" );
  });

  $( "#completedtoggle" ).click( function() {
    $( "#completedsection" ).slideToggle( "fast" );
  });

  $( "#archivetoggle" ).click( function() {
    $( "#archivesection" ).slideToggle( "fast" );
  });

  $( "#boardtoggle" ).click( function() {
    $( "#boardsection" ).slideToggle( "fast" );
  });

  $( "#chattoggle" ).click( function() {
    $( "#chatsection" ).slideToggle( "fast" );
  });
});
