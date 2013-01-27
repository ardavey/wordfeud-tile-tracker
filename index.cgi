#!/usr/bin/perl -w
use strict;
use lib qw( /home/ardavey/perlmods );

use Data::Dumper;

use CGI::Pretty;
use Wordfeud;

my $q = new CGI;
my $wf = new Wordfeud;

print $q->header();
print $q->start_html(
                      -title => 'Wordfeud stats',
                      -style => { 'src' => 'style.css' },
                    );

my $action = $q->param( "action" ) || 'login_form';

if ( $action eq 'login_form' ) {
  print $q->h2( 'Wordfeud Tile Tracker' );
  print $q->p( 'Welcome!  This is a simple Wordfeud tile counter which will allow you to view the remaining tiles on any of your current Wordfeud games.' );
  print $q->p( 'The site is under active development, and will change and evolve with no notice.  I plan to get all of the functionality in place before I "pretty it up" - function over form!' );
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

  print $q->p( 'I will try my best not to break the site so that you can continue to use it.  Please report any issues or request features <a href="http://www.ardavey.com/2013/01/21/automated-tile-tracker-beta/">here</a>.' );
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
  
  print $q->h3( 'Recently Completed Games:' );
  
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
  print_board( \@board );
}

hit_counter();

print $q->end_html();

#-------------------------------------------------------------------------------

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

sub print_board {
  my ( $board_ref ) = @_;
  my $printable_board = '';
  foreach my $r ( @$board_ref ) {
    $printable_board .= '+' . '---+' x 15 . "\n";
    my @row = map { $_ ||= ' ' } @$r;
    $printable_board .= '| ' . join( ' | ', @row ) . " |\n";
  }
  $printable_board .= '+' . '---+' x 15 . "\n";
  print $q->pre( $printable_board );
  
  #pretty_board();
}


sub pretty_board {
  my ( $board ) = @_;

print <<EOQ;
<table class="board">
  <tbody>
    <tr>
      <td class="tl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tw">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tw">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tl">&nbsp;</td>
    </tr>
    <tr>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
    </tr>
    <tr>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dw">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dw">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
    </tr>
    <tr>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dw">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
    </tr>
    <tr>
      <td class="tw">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dw">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dw">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tw">&nbsp;</td>
    </tr>
    <tr>
      <td class="">&nbsp;</td>
      <td class="tl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tl">&nbsp;</td>
      <td class="">&nbsp;</td>
    </tr>
    <tr>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
    </tr>
    <tr>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dw">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dw">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
    </tr>
    <tr>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
    </tr>
    <tr>
      <td class="">&nbsp;</td>
      <td class="tl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tl">&nbsp;</td>
      <td class="">&nbsp;</td>
    </tr>
    <tr>
      <td class="tw">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dw">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dw">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tw">&nbsp;</td>
    </tr>
    <tr>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dw">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
    </tr>
    <tr>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dw">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dw">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
    </tr>
    <tr>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
    </tr>
    <tr>
      <td class="tl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tw">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="dl">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tw">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="">&nbsp;</td>
      <td class="tl">&nbsp;</td>
    </tr>
  </tbody>
</table>
EOQ

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
  
  print $q->small( "ardavey 2013<br>" . ++$hits );
  
  # attempt to write the new hitcounter value to file
  open HITWRITE, "> wf_hits";
  print HITWRITE $hits;
  close HITWRITE;
}
