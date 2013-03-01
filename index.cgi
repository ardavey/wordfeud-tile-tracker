#!/usr/bin/perl -w

# Wordfeud Tile Tracker
#
# A simple CGI which allows the user to see the state of play
# on any of their active Wordfeud games, and view remaining tiles.
#
# Copyright 2013 Andrew Davey

use strict;
use lib qw( /home/ardavey/perlmods );

use CGI::Pretty qw( -nosticky );
use CGI::Cookie;

use Data::Dumper;

use Wordfeud;

my $q = new CGI;
my $wf = new Wordfeud;
my $log = $wf->get_log();

my $action = $q->param( "action" ) || 'login_form';

if ( $action eq 'login_form' ) {
  login_form();
}
elsif ( $action eq 'do_login' ) {
  do_login();
}
elsif ( $action eq 'game_list' ) {
  game_list();
}
elsif ( $action eq 'show_game' ) {
  show_game();
}
elsif ( $action eq 'logout' ) {
  logout();
}
else {
  start_page();
  print $q->p( 'Invalid action - returning to login page' );
  redirect( 'login_form' );
}

print $q->hr();

if ( $action ne 'login_form' ) {
  navigate_button( 'logout', 'Log out'  );
}

print $q->p( '<a href="http://www.ardavey.com/2013/01/21/automated-tile-tracker-beta/">Give feedback</a>' );
hit_counter();

print $q->end_html();

#-------------------------------------------------------------------------------
# Display the login form or, if the sessionID cookie is found, attempt to restore
# the previous session

sub login_form {
  start_page();
  
  my %cookies = CGI::Cookie->fetch();
  if ( $cookies{sessionID} ) {
    print $q->p( 'Restoring previous session' );
    redirect( 'game_list' );
  }

  Log::Log4perl::MDC->put('session', 'no session' );
  $log->info( 'Login form' );
  
  print $q->h2( 'Wordfeud Tile Tracker' );
  print $q->p( 'Welcome!  This is a simple Wordfeud tile counter which will allow you to view the remaining tiles on any of your current Wordfeud games.' );
  print $q->p( 'The site is under active development, and will change and evolve with no notice.  I plan to get all of the functionality in place before I "pretty it up" - function over form!' );
  print $q->p( 'Please enter your Wordfeud credentials.  These are only used to talk to the game server, and are NOT stored anywhere.' );
  
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

  print $q->p(
    'I will try my best not to break the site so that you can continue to use it, but it is of course presented without any guarantees.',
    'If you visit the site at some time and the colours/layout look weird, try a full refresh (Shift-Refresh or Ctrl-Refresh, depending on your browser) to reload the stylesheet.',
    'Please report any issues or request features using the feedback link below.'
  );
}


sub do_login {
  my $session_id = $wf->login_by_email( $q->param( 'email' ), $q->param( 'password' ) );
  if ( $session_id ) {
    $wf->set_session_id( $session_id );
    my $cookie = CGI::Cookie->new(
      -name => 'sessionID',
      -value => $wf->get_session_id(),
      -expires => '+1d',
    );
    start_page( $cookie );
    print $q->p( 'Logged in successfully (session: '.$wf->get_session_id().')' );
    redirect( 'game_list' );
  }
  else {
    start_page();
    print $q->p( 'Failed to log in!' );
    redirect( 'login_page' );
  }
}

#-------------------------------------------------------------------------------
# Display a list of all games which are still registered on the server

sub game_list {
  check_cookie();
  
  my $games = $wf->get_games();
  
  my @running_your_turn = ();
  my @running_their_turn = ();
  my @complete = ();
  
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

  navigate_button( 'game_list', 'Reload game list'  );

  print $q->hr();
  print $q->h3( 'Running Games:' );

  print $q->start_ul();
  print "<li>Your Turn:\n<ul>";
  if ( scalar @running_your_turn ) {
    foreach my $game ( @running_your_turn ) {
      print $q->li( game_row( $game ) );
    }
  }
  else {
    print $q->li( '<i>No games</i>' );
  }
  print "</ul>\n</li>";
  
  print "<li>Their Turn:\n<ul>";
  if ( scalar @running_their_turn ) {
    foreach my $game ( @running_their_turn ) {
      print $q->li( game_row( $game ) );
    }
  }
  else {
    print $q->li( '<i>No games</i>' );
  }
  print "</ul>\n</li>";
  print $q->end_ul();
  
  print $q->h3( 'Recently Completed Games:' );
  
  print $q->start_ul();
  
  if ( scalar @complete ) {
    foreach my $game ( @complete ) {
      print $q->li( game_row( $game ) );
    }
  }
  else {
    print $q->li( '<i>No games</i>' );
  }
  print $q->end_ul();
}  

#-------------------------------------------------------------------------------
# Show the details for a specific game

sub show_game {
  check_cookie();

  my $id = $q->param( 'id' );
  my $game = $wf->get_game( $id );
  set_my_player( $game );
  my $me = $game->{my_player};

  navigate_button( 'game_list', 'Game list'  );

  print $q->hr();
  print $q->h3( ${$game->{players}}[$me]->{username}.' ('.${$game->{players}}[$me]->{score}.') vs '
                 . ${$game->{players}}[1 - $me]->{username}.' ('.${$game->{players}}[1 - $me]->{score}.')' );
  
  #print $q->pre( Dumper($game) );

  my @board = ();
  my @rack = ();
  my @players = ();
  
  # Create an empty board - a 15x15 array. Well, an array of anonymous array references.
  # We're going to use this to print out the board later.
  foreach my $r ( 0..14 ) {
    $board[$r] = [qw( 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 )];
  }
  
  # Build a hash to track the available tiles. Start with all of them, and then
  # deduct those which are visible on the logged in player's rack and the board
  my $avail = {};
  
  foreach my $letter ( split( //, $wf->get_distribution() ) ) {
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
  
  print_tiles( \@rack, '<u>Your rack:</u>' );
  print_tiles( \@remaining, '<u>Their rack:</u>' );
  
  print_board( \@board );
  
  #print $q->hr();
  #my @chat = $wf->get_chat_messages( $id );
  #print "<pre>".Dumper( \@chat )."</pre>";
}


sub logout {
  my $cookie = CGI::Cookie->new(
    -name => 'sessionID',
    -value => '',
    -expires => '-1d',
  );
  start_page( $cookie );
  $wf->log_out();
  print $q->p( 'Logging out...' );
  redirect( 'login_form' );
}


sub start_page {
  my ( $cookie ) = @_;
  
  if ( $cookie ) {
    print $q->header( -cookie => $cookie );
  }
  else {
    print $q->header();
  }
  
  print $q->start_html(
    -title => 'Wordfeud Tile Information',
    -style => { 'src' => 'style.css' },
  );
}


sub check_cookie {
  my %cookies = CGI::Cookie->fetch();
  unless ( $cookies{sessionID} ) {
    start_page();
    print $q->p( 'Returning to login page' );
    redirect( 'login_form' );
  }
  $wf->set_session_id( $cookies{sessionID}->{value}->[0] );
  start_page( $cookies{sessionID} );
}


sub redirect {
  my ( $action ) = @_;
  
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
  
  print $q->p(
    $q->submit(
      -name => 'submit_form',
      -value => 'Continue'
    )
  );
  
  print $q->end_form();
  print '<SCRIPT LANGUAGE="JavaScript">document.forms[0].submit();</SCRIPT>';
}


sub navigate_button {
  my ( $action, $label ) = @_;
  
  $q->delete_all();
  print $q->p(
    $q->start_form(
      -name => 'navigate_button',
      -method => 'POST',
      -action => '/',
    ),
  
    $q->hidden(
      -name => 'action',
      -default => $action,
    ),
    
    $q->submit(
      -name => 'submit_form',
      -value => $label,
    ),
    
    $q->end_form(),
  );
}


sub game_row {
  my ( $game ) = @_;
  
  my $id = $game->{id};
  my $me = $game->{my_player};
  
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
    -name => 'id',
    -value => $id,
  );
  
  $game_link .= $q->submit(
    -name => 'submit_form',
    -value => 'View',
  );
    
  foreach my $player ( $me, 1 - $me ) {
    $game_link .= ' '.$game->{players}->[$player]->{username}.' ('.${$game->{players}}[$player]->{score}.') vs ';
  }
  $game_link =~ s/ vs $//;

  $game_link .= $q->end_form();
  
  return $game_link;
}

sub print_tiles {
  my ( $tiles, $label ) = @_;
  my $tile_count = scalar @$tiles;
  
  # If there are more than 7 tiles, we know that we're displaying the bag/opponent's rack combo so tailor the label accordingly
  if ( $tile_count > 7 ) {
    my $bag_count = $tile_count - 7;
    $label = "<u>Remaining tiles ($tile_count):</u><br><small><i>Bag: $bag_count; Their rack: 7</i></small>";
  }
  
  print $q->p( $label );
  
  my $count = 0;
  if ( $tile_count ) {
    print "<table><tr>\n";
    while ( my $tile = shift @$tiles ) {
      $count++;
      print "<td class='rack'>$tile</td>\n";
      if ( $count % 10 == 0 ) {
        print "</tr>\n<tr>\n";
      }
    }
    print "</tr></table>\n";
  }
  else {
    print $q->p( '<i>Empty</i>' );
  }
}

sub print_board {
  my ( $board ) = @_;

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
  
  print $q->p( '<u>Board:</u>' );
  print "<table class='board'>\n";
  foreach my $r ( 0..14 ) {
    print "<tr>\n";
    my @row = map { $_ ||= ' ' } @{$board->[$r]};
    foreach my $c ( 0..14 ) {
      if ( $row[$c] eq ' ' ) {
        print "<td class='$board_map[$r][$c]'>";
      }
      elsif ( $row[$c] ne lc( $row[$c] ) ) {
        print "<td class='tile'>";
      }
      else {
        print "<td class='tile blank'>";
      }
      print "$board->[$r][$c]</td>\n";
      
    }
    print "</tr>\n";
  }
  print "</table>\n";
}

sub set_my_player {
  my ( $game ) = @_;
  my $current_player = $game->{current_player};
  if ( exists ${$game->{players}}[$current_player]->{rack} ) {
    $game->{my_player} = $current_player;
  }
  else {
    $game->{my_player} = 1 - $current_player;
  }
}

sub hit_counter {  
  # very simple hit counter - I want to see if anyone else is using this!
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
  
  print $q->small( '&copy; ardavey 2013<br>' . ++$hits . ' page views' );
  
  # attempt to write the new hitcounter value to file
  open HITWRITE, "> wf_hits";
  print HITWRITE $hits;
  close HITWRITE;
}
