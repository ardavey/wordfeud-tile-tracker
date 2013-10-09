#!/usr/bin/perl -w

# Wordfeud Tile Tracker
#
# A simple CGI which allows the user to see the state of play
# on any of their active Wordfeud games, and view remaining tiles.
#
# Copyright 2013 Andrew Davey

use strict;
use lib qw( /home/ardavey/perlmods );
use utf8;

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
  'login_form'   => \&login_form,
  'do_login'     => \&do_login,
  'game_list'    => \&game_list,
  'archive_list' => \&archive_list,
  'show_game'    => \&show_game,
  'logout'       => \&logout,
);

( $dispatch{ $action } || \&fallback )->();

end_page();

#-------------------------------------------------------------------------------
# If we didn't receive a valid action, boot the user to the login screen
sub fallback {
  start_page();
  print $q->p( 'Invalid action - returning to login page' );
  redirect( 'login_form' );
}

#-------------------------------------------------------------------------------
# Display the login form or, if the sessionID cookie is found, attempt to restore
# the previous session
sub login_form {
  start_page();

  $wf->{log}->info( 'login_form: loading page' );
  
  my %cookies = CGI::Cookie->fetch();
  if ( $cookies{sessionID} && $cookies{uid} ) {
    print $q->p( 'Restoring previous session' );
    $wf->{log}->info( 'login_form: Found cookie - restoring session' );
    redirect( 'game_list', { uid => $cookies{uid}->{value} } );
  }
  
  print $q->hr();
  print $q->p( 'Welcome!  This is a simple Wordfeud tile counter which will allow',
               'you to view the remaining tiles on any of your current Wordfeud games.' );
  print $q->p( 'The site is under active development, and will change and evolve with no notice.' );
  print $q->p( 'Please enter your Wordfeud credentials to load your games.  These details',
               'are only used to talk to the game server - they are not stored by ardavey.com.' );
  
  $q->delete_all();
  print $q->start_form(
    -name => 'login_form',
    -method => 'POST',
    -action => '/',
  );
  print $q->p(
    'Email address: ',
    $q->textfield(
      -name => 'email',
      -value => '',
      -size => 30,
    )
  );
  print $q->p(
    'Password: ',
    $q->password_field(
      -name => 'password',
      -size => 30,
    )
  );
  print $q->hidden(
    -name => 'action',
    -default => 'do_login',
  );
  print $q->p( $q->submit(
    -name => 'submit_form',
    -value => 'Log in',
    )
  );
  print $q->end_form;

  print $q->p( 'I will try my best not to break the site so that you can continue to',
               'use it, but it is of course presented without any guarantees.' );
  print $q->p( 'If you visit the site at some time and the colours/layout look weird,',
               'try a full refresh (Shift-Refresh or Ctrl-Refresh, depending on your',
               'browser) to reload the stylesheet.' );
  print $q->p( 'Finally, please report any issues or request features using the feedback',
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
    
    start_page( [ $cookie_session, $cookie_uid ] );
    $wf->{log}->info( 'User '.$q->param( 'email' ).' logged in' );
    print $q->p( 'Logged in successfully - loading game list' );
    db_record_user( $wf->{res}->{id}, $wf->{res}->{username}, $wf->{res}->{email} );
    redirect( 'game_list', { uid => $wf->{res}->{id} } );
  }
  else {
    start_page();
    $wf->{log}->warn( 'User '.$q->param( 'email' ).' failed to log in' );
    print $q->p( 'Failed to log in!' );
    redirect( 'login_page' );
  }
}

#-------------------------------------------------------------------------------
# Display a list of all games which are still registered on the server
sub game_list {
  check_cookie();
  
  my $uid = $q->param( 'uid' );
  my $games = $wf->get_games();
  unless ( $games ) {
    print $q->p( 'Invalid session - please log in again' );
    redirect( 'logout' );
  }
  
  $wf->{log}->debug( "get_games response:" . Dumper( $wf->{res} ) );
  
  my @running_your_turn = ();
  my @running_their_turn = ();
  my @complete = ();
  
  $wf->{log}->info( 'game_list: found details for ' . scalar @$games . ' games' );
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
  
  navigate_button( 'game_list', 'Reload game list', { uid => $uid } );

  print $q->hr();
  print $q->h2( 'Running Games (' .( scalar( @running_your_turn ) + scalar( @running_their_turn ) ) . '):' );

  print $q->h3( 'Your Turn:' );
  print $q->start_ul();
  if ( scalar @running_your_turn ) {
    foreach my $game ( @running_your_turn ) {
      print_game_link( $game );
    }
  }
  else {
    print $q->li( '<i>No games</i>' );
  }
  print $q->end_ul();
  
  print $q->h3( 'Their Turn:' );
  print $q->start_ul();
  if ( scalar @running_their_turn ) {
    foreach my $game ( @running_their_turn ) {
      print_game_link( $game );
    }
  }
  else {
    print $q->li( '<i>No games</i>' );
  }
  print "</ul>\n</li>";
  print $q->end_ul();
  
  print $q->h2( 'Completed Games ('.scalar @complete.'):' );
  
  print $q->start_ul();
  if ( scalar @complete ) {
    foreach my $game ( @complete ) {
      print_game_link( $game );
      db_write_game( $game );
    }
  }
  else {
    print $q->li( '<i>No games</i>' );
  }
  print $q->end_ul();
  
  print $q->h2( 'Archived Games: (EXPERIMENTAL)' );
  print $q->p( 'This section will show you all old games which have at some time been seen',
               'in the "Completed Games" section above  i.e. it will only show games which the',
               'site was previously aware of since 17-August-13' );
  print $q->p( 'This just means that you need to log into the website',
               'at least once between completing a game and that game being deleted',
               'inside the Wordfeud app itself.' );
  print $q->p( 'At present, this is very much an experimental feature - it is vital that you let us know if',
               'you see any strange or unexpected behaviour.  If logging out and back in does not resolve',
               'your issues then please take the time to leave a post on our Facebook page with the details.' );

  print "<ul><li>\n";
  navigate_button( 'archive_list', 'View archive', { uid => $uid, token => sha1_hex( $uid . $uid ) } );
  print "</li></ul>\n";
  
}

#-------------------------------------------------------------------------------
# Display a list of archived games
sub archive_list {
  check_cookie();

  my $uid = $q->param( 'uid' );
  my $token = $q->param( 'token' );
  my $games = db_get_games( $uid );

  $wf->{log}->debug( "Fetched games from DB:" . Dumper( $games ) );

  my @gids = keys %$games;
  my $sample_game = $games->{$gids[0]};

  navigate_button( 'game_list', 'Game list', { uid => $uid } );

  print $q->hr();

  navigate_button( 'archive_list', 'Reload archive', { uid => $uid, token => $token } );

  print $q->h2( 'Archived Games ('.scalar @gids.'):' );
  
  print $q->start_ul();
  if ( $games && validate_token( $token, $uid, $sample_game ) ) {
    foreach my $gid ( reverse sort @gids ) {
      print_game_link( $games->{$gid}, $games->{$gid}->{raw}, $token );
    }
  }
  else {
    print $q->li( '<i>No games</i>' );
  }
  print $q->end_ul();
}

#-------------------------------------------------------------------------------
# Really primitive token system to mitigate against people from reading any old data from the DB
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
sub show_game {
  check_cookie();

  my $id = $q->param( 'gid' );
  my $raw_game = $q->param( 'raw_game' );
  my $token = $q->param( 'token' );
  my $game;
  
  if ( $raw_game ) {
    $game = decode_json( uncompress( decode_base64( $raw_game ) ) );
  }
  else {
    $game = $wf->get_game( $id );
    $wf->{log}->debug( "get_game response:" . Dumper( $wf->{res} ) );
    set_my_player( $game );
    set_player_info( $game );
  }
  
  $wf->{log}->debug( "show_game:" . Dumper( $game ) );

  my $me = $game->{my_player};

  $wf->{log}->info( "show_game: ID $id (" . $game->{players}[$me]->{username}
              . ' vs ' . ${$game->{players}}[1 - $me]->{username} . ')' );

  if ( $game->{from_db} ) {
    navigate_button( 'archive_list', 'Archive list', { uid => $game->{players}[$me]->{id}, token => $token } );
    print $q->hr();    
  }
  else {
    navigate_button( 'game_list', 'Game list', { uid => $game->{players}[$me]->{id} } );
    print $q->hr();
    navigate_button( 'show_game', 'Reload game', { gid => $id } );
  }
  
  
  print_player_header( $game, $me );
  print_player_header( $game, 1 - $me );
  
  my @board = ();
  my @rack = ();
  my @players = ();
  
  # Create an empty board - a 15x15 array. Well, an array of anonymous array references.
  # We're going to use this to print out the board later.
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
  
  print $q->h5( 'Language: '.$wf->{dist}->{name} );

  print_tiles( \@rack, 'Your rack:' );
  print_tiles( \@remaining, 'Their rack:' );  
  print_board( \@board, $game->{board} );
  print_last_move( $game );
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
  start_page( $cookie );
  $wf->{log}->info( 'logout' );
  print $q->p( 'Logging out...' );  
  $wf->log_out();
  redirect( 'login_form' );
}

#-------------------------------------------------------------------------------
# Very basic start of page stuff.  Connect to DB if appropoiate.
sub start_page {
  my ( $cookies ) = @_;
  
  db_connect();

  $wf->{t0} = [ gettimeofday() ];
  
  my %headers = (
    '-charset' => 'utf-8',
  );
  
  if ( $cookies ) {
    $headers{ '-cookie' } = $cookies;
  }
  print $q->header( %headers );
  
  $q->default_dtd( '-//WAPFORUM//DTD XHTML Mobile 1.2//EN http://www.openmobilealliance.org/tech/DTD/xhtml-mobile12.dtd' );
  print $q->start_html(
    -dtd => 1,
    -title => 'Wordfeud Tile Tracker',
    -style => { 'src' => 'style.css' },
    -head => [ $q->Link( { -rel => 'shortcut icon', -href => 'favicon.png' } ), ],
  );
  print <<HTML;
<div id="fb-root"></div>
<script>(function(d, s, id) {
  var js, fjs = d.getElementsByTagName(s)[0];
  if (d.getElementById(id)) return;
  js = d.createElement(s); js.id = id;
  js.src = "//connect.facebook.net/en_GB/all.js#xfbml=1";
  fjs.parentNode.insertBefore(js, fjs);
}(document, 'script', 'facebook-jssdk'));</script>
HTML

  print $q->h1( 'Wordfeud Tile Tracker' );
  
}

#-------------------------------------------------------------------------------
# Checks if we have a valid cookie - if not, we redirect to the login page
sub check_cookie {
  my %cookies = CGI::Cookie->fetch();
  unless ( $cookies{sessionID} ) {
    start_page();
    print $q->p( 'Returning to login page' );
    redirect( 'login_form' );
  }
  set_session_id( $cookies{sessionID}->{value}->[0] );
  $wf->{uid} = $cookies{uid}->{value}->[0];
  
  start_page( [ $cookies{sessionID}, $cookies{uid} ] );
}

#-------------------------------------------------------------------------------
# Really janky auto-redirect HTML page
sub redirect {
  my ( $action, $params ) = @_;
  
  $wf->{log}->info( "redirect: Redirecting to $action" );
  print $q->p( 'Hit the button below if not automatically redirected.' );

  $q->delete_all();
  print $q->start_form(
    -name => 'redirect_form',
    -method => 'POST',
    -action => '/',
  );

  print $q->hidden(
    -name => 'action',
    -default => $action,
  );
  
  foreach my $field ( keys %$params ) {
    print $q->hidden(
      -name => $field,
      -value => $params->{$field},
    );
  }  
  
  print $q->p(
    $q->submit(
      -name => 'submit_form',
      -value => 'Continue'
    )
  );
  
  print $q->end_form();
  print '<script type="text/javascript">document.forms[0].submit();</script>';
}

#-------------------------------------------------------------------------------
# Generate a button for navigating to one of the other pages
sub navigate_button {
  my ( $action, $label, $fields ) = @_;
  
  $q->delete_all();
  print "<p>\n";
  print $q->start_form(
    -name => 'navigate_button',
    -method => 'POST',
    -action => '/',
  );
  
  print $q->hidden(
    -name => 'action',
    -default => $action,
  );
  
  foreach my $field ( keys %$fields ) {
    print $q->hidden(
      -name => $field,
      -value => $fields->{$field},
    );
  }

  print $q->submit(
    -name => 'submit_form',
    -value => $label,
  );
    
  print $q->end_form();
  print "</p>\n";
}

#-------------------------------------------------------------------------------
# Prints the HTML to show a game on the game list page
sub print_game_link {
  my ( $game, $raw_game, $token ) = @_;
  
  my $id = $game->{id};
  my $me = $game->{my_player};
  my $dist = $wf->set_distribution( $game );
  
  $wf->{log}->debug( "print game link response:" . Dumper( $game ) );

  
  $q->delete_all();
  my $game_link = $q->start_form(
    -name => $id,
    -method => 'POST',
    -action => '/',
  );
  
  $game_link .= $q->hidden(
    -name => 'action',
    -value => 'show_game',
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
  
  print $q->li( $game_link );
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
    $label = $q->h4( "Remaining tiles:" );
    $trailer = $q->h5( "Bag: $bag_count; Their rack: 7" );
  }
  else {
    my $points = 0;
    foreach my $tile ( @$tiles ) {
      $points += $wf->{dist}->{points}->{$tile};
    }
    $label = $q->h4( $label );
    $trailer = $q->h5( "($points points)" );
  }
  
  print $q->p( $label );
  
  my $count = 0;
  if ( $tile_count ) {
    print "<table><tr>\n";
    while ( my $tile = shift @$tiles ) {
      $count++;
      my $print_tile = $tile;
      utf8::encode( $print_tile );
      print "<td class='rack'>$print_tile";
      if ( $tile ne '?' ) {
        print "<sub class='score'>$wf->{dist}->{points}->{$tile}</sub>";
      }
      print "</td>\n";
      if ( $count % 10 == 0 ) {
        print "</tr>\n<tr>\n";
      }
    }
    print "</tr></table>\n";
    print "$trailer\n";
  }
  else {
    print $q->p( '<i>Empty</i>' );
  }
}

#-------------------------------------------------------------------------------
# Print the player avatar, name and score for the top of the show_game page
sub print_player_header {
  my ( $game, $player ) = @_;
  
  my $html = '';
  $html .= '<a href="'. get_avatar_url( ${$game->{players}}[$player]->{id}, 'full' ) . '">';
  $html .= '<img class="av" src="' . get_avatar_url( ${$game->{players}}[$player]->{id}, 40 ) . '" /></a> ';
  $html .= ${$game->{players}}[$player]->{username} . ' (' . ${$game->{players}}[$player]->{score} . ')';
  if ( $game->{current_player} == $player ) {
    $html .= ' &larr;';
  }
  
  print $q->h2( $html );
}

#-------------------------------------------------------------------------------
# Hacky generation of HTML to show the pretty coloured board, and played tiles
sub print_board {
  my ( $board, $layout ) = @_;

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
  
  print $q->h4( 'Board:' );
  
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
  
  print $q->p( $table_html );
}

#-------------------------------------------------------------------------------
# Print details of the last move played
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
    print $q->h5( $out );
  }
}

#-------------------------------------------------------------------------------
# Print out any chat messages exchanged in the current game
sub print_chat {
  my ( $game ) = @_;
  if ( $game->{from_db} ) {
    print $q->p( { -class => 'chat' }, 'Chat messages are not available for archived games' );
  }
  else {
    my @raw_chat = $wf->get_chat_messages( $game->{id} );
    my @chat = ();
    foreach my $msg ( @{$raw_chat[0]} ) {
      my $usr = $game->{player_info}->{$msg->{sender}}->{username};
      my $time = DateTime->from_epoch( epoch => $msg->{sent}, time_zone => "UTC" );
      $time =~ s/(\d)T(\d)/$1 $2/;
      my $txt = $msg->{message};
      utf8::encode( $txt );  # should prevent wide-character warnings when emoticons are present
      push( @chat, "<small>[$time]</small> <u>$usr</u>: $txt");
    }
    print $q->h4( 'Chat messages:' );
    if ( scalar @chat ) {
      print $q->p( { -class => 'chat' }, join( "<br />\n", @chat ) );
    }
    else {
      print $q->p( { -class => 'chat' }, 'No messages' );
    }
  }
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
sub end_page {
  print $q->hr();
  
  # Facebook Like button
  print <<HTML;
<div class="fb-like" data-href="https://www.facebook.com/wordfeudtiletracker" data-width="350" data-colorscheme="dark" data-show-faces="false"></div>
HTML

  if ( $action ne 'login_form' ) {
    navigate_button( 'logout', 'Log out' );
  }

  print $q->p( 'You can leave feedback/comments/suggestions via the',
               $q->a( { href => 'http://www.facebook.com/wordfeudtiletracker' }, 'Facebook page' ),
               "or, if you don't have a Facebook account, the",
               $q->a( { href => 'http://www.ardavey.com/2013/03/11/wordfeud-tile-tracker/#respond' }, 'blog' ) );

  hit_counter();

  print $q->p( $q->small( 'Page generated in ' . tv_interval( $wf->{t0} ) . ' seconds.' ) );
  print $q->p( $q->small( 'Timestamps are presented in UTC.<br/>The site is provided free of charge with no guarantees.' ) );
  print $q->end_html();
  
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
    open HITREAD, "< wf_hits";
    $hits = <HITREAD>;
    close HITREAD;
    chomp $hits;
  }
  else {
    $hits = 0;
  }
  
  print $q->p( $q->small( '&#169; ardavey 2013<br/>' . ++$hits . ' page views' ) );
  
  # attempt to write the new hitcounter value to file
  open HITWRITE, "> wf_hits";
  print HITWRITE $hits;
  close HITWRITE;
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
# Get all games from the DB for the current user.
sub db_get_games {
  my ( $uid ) = @_;
  
  my $q = 'select id, game_data from games where user_id = ?';
  my $sth = $wf->{dbh}->prepare( $q );
  $sth->execute( $uid );
  
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
