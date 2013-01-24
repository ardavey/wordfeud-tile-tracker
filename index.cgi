#!/usr/bin/perl -w
use strict;

use Data::Dumper;

use CGI::Pretty;
use Wordfeud;

my $q = new CGI;
my $wf = new Wordfeud;

print $q->header();
print $q->start_html( -title => 'Wordfeud stats' );
  
my $action = $q->param( "action" ) || 'login_form';

if ( $action eq 'login_form' ) {
  print $q->p( 'Please enter your Wordfeud credentials.  These are only used to talk to the game server, and are NOT stored anywhere.' );
  print $q->start_form(
    -name => 'login_form',
    -method => 'POST',
  );
  print $q->p( 'Email address: '
    . $q->textfield(
      -name => 'email',
      -value => '',
      -size => 30,
    )
  );
  print $q->p( 'Password: '
	  . $q->password_field(
      -name => 'password',
      -size => 30,
    )
  );
  print $q->hidden(
    -name => 'action',
    -default => 'get_game_list',
  );
  print $q->p( $q->submit(
      -name => 'submit_form',
      -value => 'Log in',
    )
  );
  print $q->end_form;

}
elsif ( $action eq 'get_game_list' ) {
  if ( $wf->set_session_id( $wf->login_by_email( $q->param( 'email' ), $q->param( 'password' ) ) ) ) {
    print $q->p( 'Logged in successfully (session '.$wf->get_session_id().')' );
  }
  else {
    print $q->p( 'Failed to log in - go back and try again.' );
    exit 1;
  }
  
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
  
  print $q->h3( 'Recently Completed Games:s' );
  
  print $q->start_ul();
  foreach my $game ( @complete ) {
    print $q->li( printable_game( $game ) );
  }
  print $q->end_ul();
  
  print $q->hr();
}
elsif ( $action eq 'show_game' ) {
  my $id = $q->param( 'id' );
  $wf->set_session_id( $q->param( 'session' ) );
  
  my $game = $wf->get_game( $id );
  set_my_player( $game );
  my $me = $game->{my_player};
  print $q->h3( "Game $id: ".${$game->{players}}[$me]->{username}.' ('.${$game->{players}}[$me]->{score}.') vs '
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
  
  foreach my $l ( split( //, $Wordfeud::distribution ) ) {
    if ( $avail->{$l} ) {
      $avail->{$l}++;
    }
    else {
      $avail->{$l} = 1;
    }
  }
  
  foreach my $l ( @seen_tiles ) {
    $avail->{$l}--;
    if ( $avail->{$l} == 0 ) {
      delete $avail->{$l};
    }
  }
  
  my $remaining = '';
  foreach my $l ( sort keys %$avail ) {
    $remaining .= $l x $avail->{$l};
  }
  
  print $q->p( 'Your rack:<br>[<code> ' .join( ' ', @rack )." </code>]\n" );
  print $q->p( 'Remaining tiles:<br>[<code> '. join( ' ', split( //, $remaining ) ) ." </code>]\n" );
  print $q->p( 'Board:' );
  print $q->pre( printable_board( \@board ) );

}

print $q->end_html();

sub printable_game {
  my ( $game ) = @_;
  my $id = $game->{id};
  my $me = $game->{my_player};
  my $game_row = '<a href="?session='.$wf->get_session_id().'&action=show_game&id='.$id.'">Game '.$id.'</a>: ';
  foreach my $player ( $me, 1 - $me ) {
    $game_row .= $game->{players}->[$player]->{username}.' ('.${$game->{players}}[$player]->{score}.') vs ';
  }
  $game_row =~ s/ vs $//;
  return $game_row;
}

sub printable_board {
  my ( $board_ref ) = @_;
  my @board = @$board_ref;
  my $printable_board = '';
  foreach my $r ( @board ) {
    $printable_board .= '+' . '---+' x 15 . "\n";
    my @row = map { $_ ||= ' ' } @$r;
    $printable_board .= '| ' . join( ' | ', @row ) . " |\n";
  }
  $printable_board .= '+' . '---+' x 15 . "\n";
  return $printable_board;
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

