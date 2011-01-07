#!/usr/bin/perl

#############################################################################
# This script will create a development build of the extension. Without any #
# command line arguments it will include all available locales in the       #
# development build, command line arguments are interpreted as a list of    #
# locales to be included.                                                   #
#                                                                           #
# Creating a development build with all locales:                            #
#                                                                           #
#   perl make_devbuild.pl                                                   #
#                                                                           #
# Creating a development build with en-US locale only:                      #
#                                                                           #
#   perl make_devbuild.pl en-US                                             #
#                                                                           #
# Creating a development build with English, German and Russian locales:    #
#                                                                           #
#   perl make_devbuild.pl en-US de-DE ru-RU                                 #
#                                                                           #
#############################################################################

use strict;
use lib qw(buildtools);
use Packager;

my $pkg = Packager->new();
$pkg->readMetadata('metadata');

my $baseName = $pkg->{settings}{general}{basename};
my $version = $pkg->{version};

unless ($version =~ /[^\d\.]\d*$/)
{
  # Pad the version with zeroes to get version comparisons
  # right (1.2+ > 1.2.1 but 1.2.0+ < 1.2.1)
  $version .= ".0" while ($version =~ tr/././ < 2);
  $version .= "+";
}

my $build = `hg id -n`;
$build =~ s/\D//g;

my $locale = (@ARGV ? "-" . join("-", @ARGV) : "");
@ARGV = ("$baseName-$version.$build$locale.xpi", $build, @ARGV);
do 'buildtools/create_xpi.pl';
die $@ if $@;
