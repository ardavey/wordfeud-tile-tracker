#!/usr/bin/perl
use strict;
use warnings;

use 5.010;

use Data::Dumper;
use JSON qw( encode_json decode_json );
use Compress::Zlib;
use MIME::Base64;

$Data::Dumper::Sortkeys++;

my $rawdata = '';

while ( my $line = <> ) {
  $rawdata .= $line;
}

my $game = decode_json( uncompress( decode_base64( $rawdata ) ) );

say Dumper( $game );
