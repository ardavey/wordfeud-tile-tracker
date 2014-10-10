#!/usr/bin/perl -w

# Wordfeud Tile Tracker
#
# A simple CGI which allows the user to see the state of play
# on any of their active Wordfeud games, and view remaining tiles.
#
# Copyright 2013 Andrew Davey

use strict;
use lib qw( 
  /home/ardavey/perlmods
  /home/ardavey/perl5/lib/perl5
);
use utf8;

use 5.010;

use Wordfeud;
use CGI qw( -nosticky );
use CGI::Cookie;
use DateTime qw( from_epoch );
use Time::HiRes qw( gettimeofday tv_interval );
use DBI;
use JSON qw( encode_json decode_json );
use Compress::Zlib;
use MIME::Base64;
use Digest::SHA1 qw( sha1_hex );

use Log::Log4perl qw( get_logger );
use Data::Dumper;

Log::Log4perl->init( '/home/ardavey/log4perl/wf.conf' );
Log::Log4perl::MDC->put('session', 'NOSESSION' );
$Log::Log4perl::DateFormat::GMTIME = 1;

my $q = new CGI;
my $wf = new Wordfeud;

$wf->{log} = get_logger();

my $action = $q->param( "action" ) || 'login_form';

my %dispatch = (
  'login_form' => \&login_form,
  'do_login' => \&do_login,
  'show_game_list' => \&show_game_list,
  'show_archive_list' => \&show_archive_list,
  'show_game_details' => \&show_game_details,
  'logout' => \&logout,
);

( $dispatch{ $action } || \&login_form )->();

print_page_footer();


#-------------------------------------------------------------------------------
# Display the login form or, if the sessionID cookie is found, attempt to restore
# the previous session
sub login_form {
  print_page_header();

  $wf->{log}->info( 'login_form: loading page' );
  
  my %cookies = CGI::Cookie->fetch();
  if ( $cookies{sessionID} && $cookies{uid} ) {
    say $q->p( 'Restoring previous session' );
    $wf->{log}->info( 'login_form: Found cookie - restoring session' );
    redirect( 'show_game_list', { uid => $cookies{uid}->{value} } );
  }
  
  say $q->hr();
  say $q->p( 'Welcome!  This is a simple Wordfeud tile counter which will allow',
               'you to view the remaining tiles on any of your current Wordfeud games.' );
  say $q->p( 'Please enter your Wordfeud credentials to load your games.  These details',
               'are only used to talk to the game server - they are not stored by ardavey.com.' );
  
  $q->delete_all();
  say $q->start_form(
    -name => 'login_form',
    -method => 'POST',
    -action => '/',
  );
  say $q->p(
    'Email address: ',
    $q->textfield(
      -name => 'email',
      -value => '',
      -size => 30,
    )
  );
  say $q->p(
    'Password: ',
    $q->password_field(
      -name => 'password',
      -size => 30,
    )
  );
  say $q->hidden(
    -name => 'action',
    -default => 'do_login',
  );
  say $q->p( $q->submit(
    -name => 'submit_form',
    -value => 'Log in',
    )
  );
  say $q->end_form;

  say $q->p( 'Finally, please report any issues or raise request features using the feedback',
               'link below. Development of this site is driven equally by things I want',
               'to do and things the community would like!' );
}

#-------------------------------------------------------------------------------
# Actually submit the login request, then redirect to the game list if successful.
# This way, we avoid sending a new login request every time the game list page is refreshed
sub do_login {
  my $session_id = $wf->login_by_email( $q->param( 'email' ), $q->param( 'password' ) );
  
  $wf->{log}->debug( "login_by_email response:" . Dumper( $wf->{res} ) );

  if ( $session_id ) {
    set_session_id( $session_id );
    my $cookie_session = CGI::Cookie->new(
        -name => 'sessionID',
        -value => $wf->get_session_id(),
        -expires => '+2d',
    );

    my $cookie_uid = CGI::Cookie->new(
        -name => 'uid',
        -value => $wf->{res}->{id},
        -expires => '+2d',
    );
    
    print_page_header( [ $cookie_session, $cookie_uid ] );
    $wf->{log}->info( 'User '.$q->param( 'email' ).' logged in' );
    say $q->p( 'Logged in successfully - loading game list' );
    db_record_user( $wf->{res}->{id}, $wf->{res}->{username}, $wf->{res}->{email} );
    redirect( 'show_game_list', { uid => $wf->{res}->{id} } );
  }
  else {
    print_page_header();
    $wf->{log}->warn( 'User '.$q->param( 'email' ).' failed to log in with password '. '#' x length( $q->param( 'password' ) )  );
    say $q->p( 'Failed to log in!' );
    redirect( 'login_page' );
  }
}

#-------------------------------------------------------------------------------
# Display a list of all games which are still registered on the server
sub show_game_list {
  check_cookie();
  
  my $uid = $q->param( 'uid' );
  my $games = $wf->get_games();
  unless ( $games ) {
    say $q->p( 'Invalid session - please log in again' );
    redirect( 'logout' );
  }
  
  $wf->{log}->debug( "get_games response:" . Dumper( $wf->{res} ) );
  
  my @running_your_turn = ();
  my @running_their_turn = ();
  my @complete = ();
  
  $wf->{log}->info( 'show_game_list: found details for ' . scalar @$games . ' games' );
  foreach my $game ( @$games ) {
    set_my_player( $game );
    if ( $game->{is_running} ) {
      if ( $game->{current_player} == $game->{my_player} ) {
        push @running_your_turn, $game;
      }
      else {
        push @running_their_turn, $game;
      } 
    }
    else {
      push @complete, $game;
    }
  }
  
  print_navigate_button( 'show_game_list', 'Reload game list', { uid => $uid } );
  
  say $q->p( 'Click/tap on the relevant section headers (indicated by ',
             $q->img( { src => 'expand.png', alt => '[+]' } ),
             ') to show/hide the contents.'
            );

  say $q->hr();
  say $q->h2( 'Running Games (' .( scalar( @running_your_turn ) + scalar( @running_their_turn ) ).')' );
  
  say $q->start_div( { id => 'yourturncontainer' } );
  
  say $q->div( { id => 'yourturntoggle', class => 'toggleswitch' },
               $q->h3( $q->img( { src => 'expand.png', alt => '[+]' } ),
                       'Your Turn ('.scalar( @running_your_turn ).')',
                     )
             );
  
  say $q->start_ul( { id => 'yourturnsection', class => 'togglable' } );
  if ( scalar @running_your_turn ) {
    foreach my $game ( @running_your_turn ) {
      print_game_link( $game );
    }
  }
  else {
    say $q->li( $q->em( 'No games to show' ) );
  }
  say $q->end_ul();

  say $q->end_div(); # yourturncontainer
  
  say $q->start_div( { id => 'theirturncontainer' } );
  
  say $q->div( { id => 'theirturntoggle', class => 'toggleswitch' },
               $q->h3( $q->img( { src => 'expand.png', alt => '[+]' } ),
                       "Opponent's Turn (".scalar( @running_their_turn ).')',
                     )
             );

  say $q->start_ul( { id => 'theirturnsection', class => 'togglable' } );
  if ( scalar @running_their_turn ) {
    foreach my $game ( @running_their_turn ) {
      print_game_link( $game );
    }
  }
  else {
    say $q->li( $q->em( 'No games to show' ) );
  }
  say $q->end_ul();  
  say $q->end_div(); # theirturncontainer
  
  say $q->start_div( { id => 'completedcontainer' } );

  say $q->div( { id => 'completedtoggle', class => 'toggleswitch' },
               $q->h2( $q->img( { src => 'expand.png', alt => '[+]' } ),
                       'Recently Completed Games ('.scalar( @complete ).')',
                      )
             );  
    

  say $q->start_ul( { id => 'completedsection', class => 'togglable' } );
  if ( scalar @complete ) {
    foreach my $game ( @complete ) {
      print_game_link( $game );
      db_write_game( $game );
    }
  }
  else {
    say $q->li( $q->em( 'No games to show' ) );
  }
  say $q->end_ul();
  say $q->end_div(); # completedcontainer
  
  say $q->start_div( { id => 'archivecontainer' } );
  
  say $q->div( { id => 'archivetoggle', class => 'toggleswitch' },
               $q->h2( $q->img( { src => 'expand.png', alt => '[+]' } ),
                       'Archived Games',
                     ),
             );
  
  say $q->start_div( { id => 'archivesection', class => 'togglable' } );
  
  say $q->p( 'This section will show you all old games which have at some time been seen',
             'in the "Completed Games" section above.' );
  
  say $q->p( 'This means that all you need to do to archive your games is log into',
             'the website at least once between completing the game and that game being deleted',
             'inside the Wordfeud app itself - if you are a regular user then this will',
             'be no extra effort!' );

  say $q->start_ul(), $q->start_li();
  
  #say $q->h4( 'Currently undergoing maintenance.  Newly finished games will still be recorded.' );
  print_navigate_button( 'show_archive_list',
                         'View archive',
                         { uid => $uid, token => sha1_hex( $uid . $uid ), page => 1 }
                       );
  
  say $q->end_li(), $q->end_ul();
  
  say $q->end_div(); # archivesection
  say $q->end_div(); # archivecontainer
}

#-------------------------------------------------------------------------------
# Display a list of archived games
sub show_archive_list {
  check_cookie();

  my $uid = $q->param( 'uid' );
  my $token = $q->param( 'token' );
  my $page = $q->param( 'page' );
  $page ||= 1;
  
  my $gpp = 50;  # "games per page"
  my $game_count = db_get_game_count( $uid );
  
  $wf->{log}->info( "User viewing archive page $page. $game_count games in archive." );
  
  my $correction = 1;
  
  if ( ( $game_count % $gpp ) == 0 ) {
    # edge case - number of games is a multiple of the gpp
    $correction = 0;
  }
  
  my $max_page = int( $game_count / $gpp ) + $correction;

  if ( $page > $max_page ) {
    # naughty user has tried to request too high a page number - goodbye
    redirect( 'logout' );
  }
  
  # OK, get the current page's games from the DB
  my $offset = ( $page - 1 ) * $gpp;
  my $games = db_get_games( $uid, $gpp, $offset );

  $wf->{log}->debug( "Fetched games from DB:" . Dumper( $games ) );

  print_navigate_button( 'show_game_list', 'Game list', { uid => $uid } );

  my $floor = ( $page - 1 ) * $gpp + 1;
  my $ceiling = $page * $gpp;
  if ( $ceiling > $game_count ) {
    $ceiling = $game_count;
  }
  
  say $q->hr();
  
  say $q->h2( 'Archived Games' );
  
  if ( $page > 1 ) {
    print_navigate_button(
      'show_archive_list',
      '<< Previous page',
      { uid => $uid, token => $token, page => $page - 1 }
    );
  }
  
  say $q->h3( "Page $page of $max_page" );

  if ( $page < $max_page ) {
    print_navigate_button(
      'show_archive_list',
      'Next page >>',
      { uid => $uid, token => $token, page => $page + 1 }
    );
  }

  say $q->h5( "Showing $floor - $ceiling of $game_count games" );

  my @gids = keys %$games;
  my $sample_game = $games->{$gids[0]};

  say $q->start_ul();
  if ( $games && validate_token( $token, $uid, $sample_game ) ) {
    foreach my $gid ( sort { $b <=> $a } @gids ) {
      print_game_link( $games->{$gid}, $games->{$gid}->{raw}, $token, $page );
    }
  }
  else {
    say $q->li( $q->em( 'No games' ) );
  }
  say $q->end_ul();
  if ( $page > 1 ) {
    print_navigate_button(
      'show_archive_list',
      '<< Previous page',
      { uid => $uid, token => $token, page => $page - 1 }
    );
  }
  
  say $q->h3( "Page $page of $max_page" );

  if ( $page < $max_page ) {
    print_navigate_button(
      'show_archive_list',
      'Next page >>',
      { uid => $uid, token => $token, page => $page + 1 }
    );
  }
}

#-------------------------------------------------------------------------------
# Really primitive token system to mitigate against people reading any old data from the DB
sub validate_token {
  my ( $token, $uid, $game ) = @_;
  
  my $game_uid = $game->{players}[$game->{my_player}]->{id};
  my $expected_token = sha1_hex( $uid . $game_uid );
  if ( $expected_token eq $token ) {
    return 1;
  }
  return 0;
}

#-------------------------------------------------------------------------------
# Show the details for a specific game
sub show_game_details {
  check_cookie();

  my $id = $q->param( 'gid' );
  my $raw_game = $q->param( 'raw_game' );
  my $token = $q->param( 'token' );
  my $page = $q->param( 'page' );
  $page ||= 1;
  my $game;
  
  if ( $raw_game ) {
    $game = decode_json( uncompress( decode_base64( $raw_game ) ) );
  }
  else {
    $game = $wf->get_game( $id );
    set_my_player( $game );
    set_player_info( $game );
  }
  
  $wf->{log}->debug( "show_game_details:" . Dumper( $game ) );

  my $me = $game->{my_player};

  $wf->{log}->info( "show_game_details: ID $id (" . $game->{players}[$me]->{username}
              . ' vs ' . ${$game->{players}}[1 - $me]->{username} . ')' );

  if ( $game->{from_db} ) {
    print_navigate_button(
                           'show_archive_list',
                           'Archive list',
                           { uid => $game->{players}[$me]->{id},
                             token => $token,
                             page => $page,
                           }
                         );
    say $q->hr();    
  }
  else {
    print_navigate_button( 'show_game_list', 'Game list', { uid => $game->{players}[$me]->{id} } );
    say $q->hr();
    print_navigate_button( 'show_game_details', 'Reload game', { gid => $id } );
  }
  
  print_player_info( $game, $me );
  print_player_info( $game, 1 - $me );
  
  my @board = ();
  my @rack = ();
  my @players = ();
  
  # Create an empty board - a 15x15 array. Well, an array of anonymous array references.
  # We're going to use this to say out the board later.
  foreach my $r ( 0..14 ) {
    $board[$r] = [qw( 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 )];
  }
  
  $wf->set_distribution( $game );

  # Build a hash to track the available tiles. Start with all of them, and then
  # deduct those which are visible on the logged in player's rack and the board
  my $avail = {};
  
  foreach my $letter ( @{$wf->{dist}->{tileset}} ) {
    if ( $avail->{$letter} ) {
      $avail->{$letter}++;
    }
    else {
      $avail->{$letter} = 1;
    }
  }

  # Determine the logged in player's rack
  foreach my $player ( @{$game->{players}} ) {
    if ( exists $player->{rack} ) {
      @rack = @{$player->{rack}};
      @rack = map { $_ = ( length $_ ) ? $_ : '?' } @rack;
      foreach my $tile ( @rack ) {
        $avail->{$tile}--;
      }
      last;
    }
  }
  
  # Now we're going to populate our board array, and deduct all of the tiles on
  # the board from the overall tile distribution
  foreach my $tile ( @{$game->{tiles}} ) {
    my @tile_params = @$tile;
    if ( $tile_params[3] ) {
      # This denotes that the current tile is a wildcard
      @board[$tile_params[1]]->[$tile_params[0]] = lc( $tile_params[2] );
      $avail->{'?'}--;
    }
    else {
      @board[$tile_params[1]]->[$tile_params[0]] = $tile_params[2];
      $avail->{$tile_params[2]}--;
    }
  }
  
  # Finally, build an array of the remaining tiles
  my @remaining = ();
  foreach my $letter ( sort keys %$avail ) {
    foreach ( 1..$avail->{$letter} ) {
      push @remaining, $letter;
    }
  }
  
  say $q->h5( 'Language: '.$wf->{dist}->{name} );

  print_tiles( \@rack, 'Your rack:' );
  print_tiles( \@remaining, "Opponent's rack:" );  
  print_board_and_last_move( \@board, $game );
  print_chat( $game );
}

#-------------------------------------------------------------------------------
# This just clears the cookie - there's nothing to do server-side.  People like
# the peace of mind associated with being able to "remove any details" about a site
sub logout {
  my $cookie = CGI::Cookie->new(
    -name => 'sessionID',
    -value => '',
    -expires => '-1d',
  );
  print_page_header( $cookie );
  $wf->{log}->info( 'logout' );
  say $q->p( 'Logging out...' );  
  $wf->log_out();
  redirect( 'login_form' );
}

#-------------------------------------------------------------------------------
# Very basic start of page stuff.  Connect to DB if appropriate.
sub print_page_header {
  my ( $cookies ) = @_;
  
  db_connect();

  $wf->{t0} = [ gettimeofday() ];
  
  my %headers = (
    '-charset' => 'utf-8',
  );
  
  if ( $cookies ) {
    $headers{ '-cookie' } = $cookies;
  }
  say $q->header( %headers );
  
  $q->default_dtd( '-//WAPFORUM//DTD XHTML Mobile 1.2//EN http://www.openmobilealliance.org/tech/DTD/xhtml-mobile12.dtd' );
  
  say $q->start_html(
    -dtd => 1,
    -title => 'Wordfeud Tile Tracker',
    -style => { 'src' => "style.css?v=$$" },
    -head => [ $q->Link( { -rel => 'shortcut icon', -href => 'favicon.png' } ), ],
  );

  say qq{ <script src="http://code.jquery.com/jquery-1.11.0.min.js"></script> };
  say qq{ <script src="wordfeudtiletracker.js?v=$$"></script> };

  say $q->h1( 'Wordfeud Tile Tracker' );  

  # Facebook "Like" button
  #say $q->start_div( { 'width' => '100%' } );
  #say $q->div( { 'id' => 'fb-root' }, '' );
  #say $q->div( {
  #               'class' => 'fb-like',
  #               'data-href' => 'https://www.facebook.com/wordfeudtiletracker',
  #               'data-layout' => 'standard',
  #               'data-colorscheme' => 'dark',
  #               'data-action' => 'like',
  #               'data-showfaces' => 'false',
  #               'data-share' => 'true',
  #              }, '' );
  #say $q->end_div();
  
}

#-------------------------------------------------------------------------------
# Checks if we have a valid cookie - if not, we redirect to the login page
sub check_cookie {
  my %cookies = CGI::Cookie->fetch();
  unless ( $cookies{sessionID} ) {
    print_page_header();
    say $q->p( 'Previous session has expired - returning to login page' );
    redirect( 'login_form' );
  }
  set_session_id( $cookies{sessionID}->{value}->[0] );
  $wf->{uid} = $cookies{uid}->{value}->[0];
  
  print_page_header( [ $cookies{sessionID}, $cookies{uid} ] );
}

#-------------------------------------------------------------------------------
# Really janky auto-redirect HTML page
sub redirect {
  my ( $action, $params ) = @_;
  
  $wf->{log}->info( "redirect: Redirecting to $action" );
  say $q->p( 'Hit the button below if not automatically redirected.' );

  $q->delete_all();
  say $q->start_form(
    -name => 'redirect_form',
    -method => 'POST',
    -action => '/',
  );

  say $q->hidden(
    -name => 'action',
    -default => $action,
  );
  
  foreach my $field ( keys %$params ) {
    say $q->hidden(
      -name => $field,
      -value => $params->{$field},
    );
  }  
  
  say $q->p(
    $q->submit(
      -name => 'submit_form',
      -value => 'Continue'
    )
  );
  
  say $q->end_form();
  say '<script type="text/javascript">document.forms[0].submit();</script>';
}

#-------------------------------------------------------------------------------
# Generate a button for navigating to one of the other pages
sub print_navigate_button {
  my ( $action, $label, $fields ) = @_;
  
  $q->delete_all();
  say $q->start_p();
  say $q->start_form(
    -name => 'navigate_button',
    -method => 'POST',
    -action => '/',
  );
  
  say $q->hidden(
    -name => 'action',
    -default => $action,
  );
  
  foreach my $field ( keys %$fields ) {
    say $q->hidden(
      -name => $field,
      -value => $fields->{$field},
    );
  }

  say $q->submit(
    -name => 'submit_form',
    -value => $label,
  );
    
  say $q->end_form();
  say $q->end_p();
}

#-------------------------------------------------------------------------------
# Prints the HTML to show a game on the game list page
sub print_game_link {
  my ( $game, $raw_game, $token, $page ) = @_;
  
  my $id = $game->{id};
  my $me = $game->{my_player};
  my $dist = $wf->set_distribution( $game );
  
  $q->delete_all();
  my $game_link = $q->start_form(
    -name => $id,
    -method => 'POST',
    -action => '/',
  );
  
  $game_link .= $q->hidden(
    -name => 'action',
    -value => 'show_game_details',
  );
  
  $game_link .= $q->hidden(
    -name => 'gid',
    -value => $id,
  );
  
  if ( $raw_game ) {
    $game_link .= $q->hidden(
      -name => 'raw_game',
      -value => $raw_game,
    );
  }
  
  if ( $token ) {
    $game_link .= $q->hidden(
      -name => 'token',
      -value => $token,
    );  
  }
  
  if ( $page ) {
    $game_link .= $q->hidden(
      -name => 'page',
      -value => $page,
    );  
  }
  
  $game_link .= $q->submit(
    -name => 'submit_form',
    -value => 'View',
  );
  
  my $class = '';
  
  if ( $game->{players}[$me]->{score} > $game->{players}[1 - $me]->{score} ) {
    $class = 'winning';
  }
  elsif ( $game->{players}[$me]->{score} < $game->{players}[1 - $me]->{score} ) {
    $class = 'losing';
  }

  $game_link .= "<span class='$class'>";
  $game_link .= ' ' . $game->{players}[$me]->{username} . ' vs ' . $game->{players}[1 - $me]->{username}
             .  ' (' . $game->{players}[$me]->{score} . ' - ' . $game->{players}[1 - $me]->{score} . ')';  
  $game_link .= '<br />';
  
  my $started = DateTime->from_epoch( epoch => $game->{created}, time_zone => "UTC" );
  #my $updated = DateTime->from_epoch( epoch => $game->{updated}, time_zone => "UTC" );
  $started =~ s/(\d)T(\d)/$1 $2/;
  #$updated =~ s/(\d)T(\d)/$1 $2/;
  
  $game_link .= $q->small(
                          $wf->{dist}->{name},
                          ( $game->{board} == 0 ) ? ' &mdash; Standard board' : ' &mdash; Random board',
                          "<br/>Started: $started" # &mdash; Last Move: $updated"
                          );
  $game_link .= '</span>';

  $game_link .= $q->end_form();
  
  say $q->li( $game_link );
}

#-------------------------------------------------------------------------------
# Prints the provided array of letters in rows of 10
sub print_tiles {
  my ( $tiles, $label ) = @_;
  my $trailer;
  
  my $tile_count = scalar @$tiles;
  
  # If there are more than 7 tiles, we know that we're displaying the bag/opponent's
  # rack combo so override the label accordingly
  if ( $tile_count > 7 ) {
    my $bag_count = $tile_count - 7;
    $label = $q->h4( 'Remaining tiles:' );
    $trailer = $q->h5( "Bag: $bag_count; Opponent's rack: 7" );
  }
  else {
    my $points = 0;
    foreach my $tile ( @$tiles ) {
      $points += $wf->{dist}->{points}->{$tile};
    }
    $label = $q->h4( $label );
    $trailer = $q->h5( "($points points)" );
  }
  
  say $q->p( $label );
  
  my $count = 0;
  if ( $tile_count ) {
    say $q->start_table();
    say '<tr>';
    while ( my $tile = shift @$tiles ) {
      $count++;
      my $print_tile = $tile;
      utf8::encode( $print_tile );
      say $q->start_td( { class => 'rack' } );
      print $print_tile;
      if ( $tile ne '?' ) {
        say $q->Sub( { class => 'score' }, $wf->{dist}->{points}->{$tile} );
      }
      say $q->end_td();
      if ( $count % 10 == 0 ) {
        say '</tr>', '<tr>';
      }
    }
    say '</tr>', $q->end_table();
    say "$trailer";
  }
  else {
    say $q->p( $q->em( 'Empty' ) );
  }
}

#-------------------------------------------------------------------------------
# Say the player avatar, name and score for the top of the show_game_details page
sub print_player_info {
  my ( $game, $player ) = @_;
  
  my $html = '';
  $html .= '<a href="'. get_avatar_url( ${$game->{players}}[$player]->{id}, 'full' ) . '">';
  $html .= '<img class="av" src="' . get_avatar_url( ${$game->{players}}[$player]->{id}, 40 ) . '" /></a> ';
  $html .= ${$game->{players}}[$player]->{username} . ' (' . ${$game->{players}}[$player]->{score} . ')';
  if ( $game->{current_player} == $player ) {
    $html .= ' &larr;';
  }
  
  say $q->h2( $html );
}

#-------------------------------------------------------------------------------
# Hacky generation of HTML to show the pretty coloured board, and played tiles
sub print_board_and_last_move {
  my ( $board, $game ) = @_;

  my $layout = $game->{board};
  
  # This 2D array represents the style to be applied to the respective squares on the board.
  # This is pretty ugly and evil, but it's amazing what you can come up with in a spare half
  # hour in Starbucks!
  my @board_map = (
    [ qw( tl e e e tw e e dl e e tw e e e tl ) ],
    [ qw( e dl e e e tl e e e tl e e e dl e ) ],
    [ qw( e e dw e e e dl e dl e e e dw e e ) ],
    [ qw( e e e tl e e e dw e e e tl e e e ) ],
    [ qw( tw e e e dw e dl e dl e dw e e e tw ) ],
    [ qw( e tl e e e tl e e e tl e e e tl e ) ],
    [ qw( e e dl e dl e e e e e dl e dl e e ) ],
    [ qw( dl e e dw e e e c e e e dw e e dl ) ],
    [ qw( e e dl e dl e e e e e dl e dl e e ) ],
    [ qw( e tl e e e tl e e e tl e e e tl e ) ],
    [ qw( tw e e e dw e dl e dl e dw e e e tw ) ],
    [ qw( e e e tl e e e dw e e e tl e e e ) ],
    [ qw( e e dw e e e dl e dl e e e dw e e ) ],
    [ qw( e dl e e e tl e e e tl e e e dl e ) ],
    [ qw( tl e e e tw e e dl e e tw e e e tl ) ],
  );
  
  my $table_html = "<table class='board'>\n";
  foreach my $r ( 0..14 ) {
    $table_html .= "<tr>\n";
    my @row = map { $_ ||= ' ' } @{$board->[$r]};
    foreach my $c ( 0..14 ) {
      my $tile = $board->[$r][$c];
      my $square = '';
      if ( $layout == 0 ) {
        $square = $board_map[$r][$c];
      }
      else {
        $square = 'e';
      }
      
      my $print_tile = $tile;
      utf8::encode( $print_tile );
      
      if ( $row[$c] eq ' ' ) {
        $table_html .= "<td class='$square'>";
      }
      elsif ( $row[$c] ne lc( $row[$c] ) ) {
        $table_html .= "<td class='tile'>";
      }
      else {
        $table_html .= "<td class='tile blank'>";
      }
      
      $table_html .= uc( $print_tile );
      if ( $tile ne ' ' && $tile eq uc( $tile ) ) {
        $table_html .= "<sub class='score'>".$wf->{dist}->{points}->{"$tile"}."</sub>";
      }
      
      $table_html .= "</td>\n";
    }
    $table_html .= "</tr>\n";
  }
  $table_html .= "</table>\n";
  
  say $q->start_div( { id => 'boardcontainer' } );
  
  say $q->div( { id => 'boardtoggle', class => 'toggleswitch' },
               $q->h4( $q->img( { src => 'expand.png', alt => '[+]' } ),
                       'Board:',
                     ),
             );
  
  say $q->start_div( { id => 'boardsection', class => 'togglable' } );
  
  print_last_move( $game );
  say $q->p( $table_html );
  
  say $q->end_div(); # boardsection
  say $q->end_div(); # boardcontainer
}

#-------------------------------------------------------------------------------
# Say details of the last move played
sub print_last_move {
  my ( $game ) = @_;
  
  my $out = '';

  if ( exists $game->{last_move} ) {
    my $id = $game->{last_move}->{user_id};
    my $player = $game->{player_info}->{$id}->{username};
    $out .= 'Last move: ';
    if ( $game->{last_move}->{move_type} eq 'move' ) {
      my $points = $game->{last_move}->{points};
      $out .= "$player played " . $game->{last_move}->{main_word};
      $out .= " for $points point";
      $out .= ( $points > 1 ) ? 's' : '';
    }
    elsif ( $game->{last_move}->{move_type} eq 'swap' ) {
      my $count = $game->{last_move}->{tile_count};
      $out .= "<i>$player swapped $count tile";
      $out .= ( $count > 1 ) ? 's' : '';
      $out .= '</i>';
    }
    elsif ( $game->{last_move}->{move_type} eq 'pass' ) {
      $out .= "<i>$player passed</i>";
    }
    elsif ( $game->{last_move}->{move_type} eq 'resign' ) {
      $out .= "<i>$player resigned</i>";
    }
    else {
      return;
    }
    say $q->h5( $out );
  }
}

#-------------------------------------------------------------------------------
# Say out any chat messages exchanged in the current game
sub print_chat {
  my ( $game ) = @_;
  
  my @chat = ();
  
  if ( ! $game->{from_db} ) {
    my @raw_chat = $wf->get_chat_messages( $game->{id} );
    foreach my $msg ( @{$raw_chat[0]} ) {
      my $usr = $game->{player_info}->{$msg->{sender}}->{username};
      my $time = DateTime->from_epoch( epoch => $msg->{sent}, time_zone => "UTC" );
      $time =~ s/(\d)T(\d)/$1 $2/;
      my $txt = $msg->{message};
      utf8::encode( $txt );  # should prevent wide-character warnings when emoticons are present
      push( @chat, "<small>[$time]</small> <u>$usr</u>: $txt");
    }
  }
  
  say $q->start_div( { id => 'chatcontainer' } );
  
  say $q->div( { id => 'chattoggle', class => 'toggleswitch' },
               $q->h4( $q->img( { src => 'expand.png', alt => '[+]' } ),
                       'Chat messages ('.scalar( @chat ).'):',
                     ),
             );
  
  say $q->start_p( { id => 'chatsection' , class => 'chat togglable' } );
  
  if ( $game->{from_db} ) {
    say 'Chat messages are not available for archived games';
  }  
  elsif ( scalar @chat ) {
    say join( "<br />\n", @chat );
  }
  else {
    say 'No messages';
  }
  
  say $q->end_p();
  
  say $q->end_div(); # chatcontainer
}

#-------------------------------------------------------------------------------
# Set the session ID in both the object and the log4perl MDC
sub set_session_id {
  my ( $session_id ) = @_;
  Log::Log4perl::MDC->put('session', $session_id );
  $wf->set_session_id( $session_id );
}

#-------------------------------------------------------------------------------
# Utility method to set the ID of "you" - used for ordering names on game list
# so that the logged in player is always shown first
sub set_my_player {
  my ( $game ) = @_;
  my $current_player = $game->{current_player};
  if ( exists $game->{players}[$current_player]->{rack} ) {
    $game->{my_player} = $current_player;
  }
  else {
    $game->{my_player} = 1 - $current_player;
  }
}

#-------------------------------------------------------------------------------
# Map user IDs to names
sub set_player_info {
  my ( $game ) = @_;
  foreach my $player ( @{ $game->{players} } ) {
    $game->{player_info}->{$player->{id}}->{username} = $player->{username};
    if ( exists $player->{fb_user_id} ) {
      $game->{player_info}->{$player->{id}}->{fb_id} = $player->{fb_user_id};
    }
  }
}

#-------------------------------------------------------------------------------
# Returns the URL for the supplied user's avatar
sub get_avatar_url {
  my ( $id, $size ) = @_;
  # Sizes '40', '60' and 'full' are known to work
  return "http://avatars.wordfeud.com/$size/$id";
}

#-------------------------------------------------------------------------------
# Add the footer and wrap up our HTML
sub print_page_footer {
  say $q->hr();
  
  if ( $action ne 'login_form' ) {
    print_navigate_button( 'logout', 'Log out' );
  }

  say $q->p( 'You can leave feedback/comments/suggestions via the',
             $q->a( { href => 'http://www.facebook.com/wordfeudtiletracker' }, 'Facebook page' ) . '.'
           );

  hit_counter();

  say $q->p( $q->small( 'Page generated in ' . tv_interval( $wf->{t0} ) . ' seconds.' ) );
  say $q->p( $q->small( 'Timestamps are presented in UTC.<br/>The site is provided free of charge with no guarantees.' ) );
  say $q->end_html();
  
  if ( $wf->{dbh} ) {
    $wf->{log}->debug( 'Disconnecting from DB' );
    $wf->{dbh}->disconnect();
  }
}

#-------------------------------------------------------------------------------
# Very simple hit counter - I want to see if anyone else is using this!
sub hit_counter {  
  my $hits;
  
  # 'hits' is a txt file where the first row represents the number of hits
  if ( -e "./wf_hits" ) {
    open HITREAD, "< wf_hits" or $wf->{log}->error( "Unable to open counter file for read: $!" );
    $hits = <HITREAD>;
    close HITREAD;
    chomp $hits;
  }
  else {
    $wf->{log}->error( 'Can not find counter file' );
  }
  
  my $rewrite_hits = 1;
  
  if ( $hits ) {
    $hits++;
  }
  else {
    $hits = 'many many';
    $rewrite_hits = 0;
  }
  
  say $q->p( $q->small( '&#169; ardavey 2013-14<br/>' . $hits . ' page views' ) );
  
  if ( $rewrite_hits ) {
    # attempt to write the new hitcounter value to file
    open HITWRITE, "> wf_hits" or $wf->{log}->error( "Unable to open counter file for write: $!" );
    say HITWRITE $hits;
    close HITWRITE;
  }
  
}


#===============================================================================
# Database stuff follows...
#===============================================================================

#-------------------------------------------------------------------------------
# Does what it says on the tin...
sub db_connect {
  $wf->{log}->debug( 'Connecting to DB' );
  # SQLite will do for now - the site's relatively low volume
  my $dsn = 'dbi:SQLite:dbname=/home/ardavey/db/wordfeudtracker.db';
  my $user = undef;
  my $pass = undef;
  my $opts = {
    AutoCommit => 1,
    RaiseError => 1,
    sqlite_see_if_its_a_number => 1,
  };
  $wf->{dbh} = DBI->connect( $dsn, $user, $pass, $opts );
}


#-------------------------------------------------------------------------------
# Record the logged in user's ID and username
sub db_record_user {
  my ( $id, $username, $email ) = @_;
  my $last_login = time();
  my $q = 'replace into users ( id, username, email, last_login ) values ( ?, ?, ?, ? )';
  $wf->{log}->debug( "Running query: [$q]");
  my $sth = $wf->{dbh}->prepare( $q );
  $sth->execute( $id, $username, $email, $last_login );
}

#-------------------------------------------------------------------------------
# Get just a count of the games in the DB for the current user.
sub db_get_game_count {
  my ( $uid ) = @_;
  
  my $q = 'select count() from games where user_id = ?';
  my $sth = $wf->{dbh}->prepare( $q );
  $sth->execute( $uid );
  
  my ( $count ) = $sth->fetchrow_array();
  
  return $count;
}

#-------------------------------------------------------------------------------
# Get all games from the DB for the current user, with pagination.
sub db_get_games {
  my ( $uid, $limit, $offset ) = @_;
  
  my $sql = 'select id, game_data from games where user_id = ? order by id desc limit ?, ?';
  my @bv = ( $uid, $offset, $limit );
  $wf->{log}->info( 'db_get_games executing: '.$sql.' [ '.join( ',', @bv ).' ]' );
  my $sth = $wf->{dbh}->prepare( $sql );
  $sth->execute( @bv );
  
  my $games = {};
  while ( my ( $gid, $raw_game ) = $sth->fetchrow_array() ) {
    $games->{$gid} = decode_json( uncompress( decode_base64( $raw_game ) ) );
    $games->{$gid}->{raw} = $raw_game;
  }
  
  return $games;
}

#-------------------------------------------------------------------------------
# Record the given game to the DB, compressed and encoded
sub db_write_game {
  my ( $game ) = @_;
  $wf->{log}->debug( 'In db_write_game' );
  my $user_id = $game->{players}[$game->{my_player}]->{id};
  my $game_id = $game->{id};
  my $finished_time = $game->{updated};

  my $q = 'select game_data from games where id=? and user_id=?';
  my $sth = $wf->{dbh}->prepare( $q );
  $sth->execute( $game_id, $user_id );
  my @res = $sth->fetchrow_array();
  
  if ( $res[0] ) {
    # Game is already in DB for this user
    $wf->{log}->info( "Game $game_id already in DB for user $user_id" );
  }
  else {
    # Easier to store this stuff with the game rather than work it out later
    my $full_game = $wf->get_game( $game->{id} );
    $full_game->{from_db} = 1;
    set_my_player( $full_game );
    set_player_info( $full_game );

    $full_game = encode_base64( compress( encode_json( $full_game ) ) );  
    
    $wf->{log}->info( "Recording game $game_id to DB for user $user_id" );
    $q = 'replace into games ( id, user_id, finished_time, game_data ) values ( ?, ?, ?, ? )';
    $sth = $wf->{dbh}->prepare( $q );
    $sth->execute( $game_id, $user_id, $finished_time, $full_game );
  }
}
