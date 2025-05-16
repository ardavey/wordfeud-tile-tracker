#!/usr/bin/perl
use strict;
use warnings;

use LWP::Simple;

my $size = 0;

while ( 1 ) {
  my $res = head( "http://avatars.wordfeud.com/$size/11584515" );
  if ( $res ) {
    print "Valid: $size\n";
  }
  $size++;
}
