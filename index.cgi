#!/usr/bin/perl -w
use strict;
use lib qw( /home/ardavey/perlmods );

use CGI::Pretty;
use CGI::Cookie;

use Log::Log4perl qw( get_logger );
use Data::Dumper;

use Wordfeud;

my $q = new CGI;
my $wf = new Wordfeud;
my $log = get_logger( 'logger.conf' );

my $debug = 0;

my $action = $q->param( "action" ) || 'login_form';

if ( $action eq 'login_form' ) {
  start_page();
  
  my %cookies = CGI::Cookie->fetch();
  if ( exists $cookies{sessionID} ) {
    print $q->p( 'Restoring previous session' );
    redirect( 'game_list' );
  }

  print $q->h2( 'Wordfeud Tile Tracker' );
  print $q->p( 'Welcome!  This is a simple Wordfeud tile counter which will allow you to view the remaining tiles on any of your current Wordfeud games.' );
  print $q->p( 'The site is under active development, and will change and evolve with no notice.  I plan to get all of the functionality in place before I "pretty it up" - function over form!' );
  print $q->p( 'Please enter your Wordfeud credentials.  These are only used to talk to the game server, and are NOT stored anywhere.' );
  
  $q->delete_all();
  print $q->start_form(
    -name => 'login_form',
    -method => 'POST',
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
    'Please report any issues or request features using the feedback link below.'
  );
}
elsif ( $action eq 'do_login' ) {
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
elsif ( $action eq 'game_list' ) {
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

  print $q->hr();
  print $q->h3( 'Running Games:' );

  print $q->start_ul();
  print "<li>Your Turn:\n<ul>";
  foreach my $game ( @running_your_turn ) {
    print $q->li( printable_game( $game ) );
  }
  print "</ul>\n</li>";
  
  print "<li>Their Turn:\n<ul>";
  foreach my $game ( @running_their_turn ) {
    print $q->li( printable_game( $game ) );
  }
  print "</ul>\n</li>";
  print $q->end_ul();
  
  print $q->h3( 'Recently Completed Games:' );
  
  print $q->start_ul();
  foreach my $game ( @complete ) {
    print $q->li( printable_game( $game ) );
  }
  print $q->end_ul();
  
  print $q->hr();
}
elsif ( $action eq 'show_game' ) {
  check_cookie();
  
  print $q->small(
    $q->a(
      {
        href => '?action=game_list',
      },
      '<-- back to game list'
    )
  );
  
  my $id = $q->param( 'id' );
  my $game = $wf->get_game( $id );
  set_my_player( $game );
  my $me = $game->{my_player};
  print $q->h3( ${$game->{players}}[$me]->{username}.' ('.${$game->{players}}[$me]->{score}.') vs '
                 . ${$game->{players}}[1 - $me]->{username}.' ('.${$game->{players}}[1 - $me]->{score}.')' );
  
  #print $q->pre( Dumper($game) );

  my @seen_tiles = ();
  my @board = ();
  my @rack = ();
  
  # create an empty board
  foreach my $r ( 0..14 ) {
    $board[$r] = [qw( 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 )];
  }
  my @players = ();
  
  foreach my $player ( @{$game->{players}} ) {
    if ( exists $player->{rack} ) {
      @rack = @{$player->{rack}};
      @rack = map { $_ = ( length $_ ) ? $_ : '?' } @rack;
      push @seen_tiles, @rack;
    }
  }
  
  foreach my $tile ( @{$game->{tiles}} ) {
    if ( @$tile[3] ) {
      @board[@$tile[1]]->[@$tile[0]] = lc( @$tile[2] );
      push @seen_tiles, '?';
    }
    else { 
      @board[@$tile[1]]->[@$tile[0]] = @$tile[2];
      push @seen_tiles, @$tile[2];
    }
  }

  my $avail = {};
  
  foreach my $letter ( split( //, $Wordfeud::distribution ) ) {
    if ( $avail->{$letter} ) {
      $avail->{$letter}++;
    }
    else {
      $avail->{$letter} = 1;
    }
  }
  
  foreach my $letter ( @seen_tiles ) {
    $avail->{$letter}--;
    if ( $avail->{$letter} == 0 ) {
      delete $avail->{$letter};
    }
  }
  
  my $remaining = '';
  foreach my $letter ( sort keys %$avail ) {
    $remaining .= $letter x $avail->{$letter};
  }
  
  print $q->p( 'Your rack:<br>[<code> ' .join( ' ', @rack )." </code>]\n" );
  print $q->p( 'Remaining tiles:<br>[<code> '. join( ' ', split( //, $remaining ) ) ." </code>]\n" );
  print $q->p( 'Board:' );
  pretty_board( \@board );
}
elsif ( $action eq 'logout' ) {
  my $cookie = CGI::Cookie->new(
    -name => 'sessionID',
    -value => '',
    -expires => '-1d',
  );
  start_page( $cookie );
  print $q->p( 'Logging out...' );
  redirect( 'login_form' );
}
else {
  start_page();
  print $q->p( 'Invalid action - returning to login page' );
  redirect( 'login_form' );
}

print $q->small(
  $q->a(
    { href => '?action=logout' },
    'Log out',
  )
);

print $q->p( '<a href="http://www.ardavey.com/2013/01/21/automated-tile-tracker-beta/">Give feedback</a>' );
hit_counter();

print $q->end_html();

#-------------------------------------------------------------------------------

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
  unless ( exists $cookies{sessionID} ) {
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
  );

  print $q->hidden(
    -name => 'session',
    -default => $wf->get_session_id(),
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
  print $q->end_form;
  print '<SCRIPT LANGUAGE="JavaScript">document.forms[0].submit();</SCRIPT>';
}

sub printable_game {
  my ( $game ) = @_;
  my $id = $game->{id};
  my $me = $game->{my_player};
  my $game_row = '<a href="?action=show_game&id='.$id.'">View</a> ';
  foreach my $player ( $me, 1 - $me ) {
    $game_row .= $game->{players}->[$player]->{username}.' ('.${$game->{players}}[$player]->{score}.') vs ';
  }
  $game_row =~ s/ vs $//;
  return $game_row;
}

sub print_board {
  my ( $board_ref ) = @_;
  my $board_colour = 'lightgray';
  my $letter_colour = 'black';
  my $printable_board = "<font color='$board_colour'>";
  foreach my $r ( @$board_ref ) {
    $printable_board .= '+' . '---+' x 15 . "\n";
    my @row = map { $_ ||= ' ' } @$r;
    @row = map { "<font color='$letter_colour'>$_</font>" } @row;
    $printable_board .= '| ' . join( ' | ', @row ) . " |\n";
  }
  $printable_board .= '+' . '---+' x 15 . "</font>\n";
  print $q->pre( $printable_board );
}

sub pretty_board {
  my ( $board_ref ) = @_;

  print "<table class='board'>\n";
  foreach my $r ( @$board_ref ) {
    print "<tr>\n";
    my @row = map { $_ ||= ' ' } @$r;
    @row = map { ( $_ eq ' ' ) ? "<td>$_</td>" : ( lc( $_ ) ne $_ ) ? "<td class='tile'>$_</td>" : "<td class='tile blank'>$_</td>" } @row;
    print join( "\n", @row );
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
    my @in = <HITREAD>;
    close HITREAD;
    chomp @in;
    $hits = $in[0];
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
