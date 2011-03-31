#!/usr/bin/perl

#############################################################################
# This script will create an extension build. Usually, this script          #
# shouldn't be run directly, use make_devbuild.pl instead.                  #
#############################################################################

use strict;
use warnings;
use lib qw(buildtools);
use Packager;

my %params = ();

my $xpiFile = shift @ARGV;
if (@ARGV && $ARGV[0] =~ /^\d+$/)
{
  $params{devbuild} = $ARGV[0];
  shift @ARGV;
}
else
{
  $params{postprocess_line} = \&removeTimeLine;
}

$params{locales} = \@ARGV if @ARGV;

my $pkg = Packager->new(\%params);
$pkg->readMetadata('metadata');
$pkg->readLocales('chrome/locale') unless exists $params{locales};
$pkg->readLocaleData('chrome/locale');

my $baseName = $pkg->{settings}{general}{basename};
$xpiFile = "$baseName.xpi" unless $xpiFile;

chdir('chrome');
$pkg->makeJAR("$baseName.jar", 'content', 'skin', 'locale', '-/tests', '-/mochitest', '-/.incomplete', '-/meta.properties');
chdir('..');

my @files = grep {-e $_} ('components', <modules/*.jsm>, 'defaults', 'bootstrap.js', 'chrome.manifest', 'icon.png', 'icon64.png');
@files = grep {$_ ne "modules/TimeLine.jsm"} @files unless exists($params{devbuild});

$pkg->makeXPI($xpiFile, "chrome/$baseName.jar", @files);
unlink("chrome/$baseName.jar");

sub removeTimeLine
{
  my ($file, $line) = @_;

  return "\n" if $file =~ /\.jsm?$/ && $line =~ /\b[tT]imeLine\.(\w+)\(/;
  return "\n" if $file =~ /\.jsm?$/ && $line =~ /Cu\.import\([^()]*\bTimeLine\.jsm\"\)/;

  return $line;
}
