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
if (@ARGV && $ARGV[0] =~ /^\+/)
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
$pkg->readVersion('version');
$pkg->readBasename('chrome.manifest');
$pkg->readLocales('chrome/locale') unless exists $params{locales};
$pkg->readLocaleData('chrome/locale', 'install.rdf');

$xpiFile = "$pkg->{baseName}.xpi" unless $xpiFile;

chdir('chrome');
$pkg->makeJAR("$pkg->{baseName}.jar", 'content', 'skin', 'locale', '-/tests', '-/mochitest', '-/.incomplete', '-/meta.properties');
chdir('..');

my @files = grep {-e $_} ('components', 'modules', 'defaults', 'install.rdf', 'chrome.manifest', 'icon.png');

$pkg->makeXPI($xpiFile, "chrome/$pkg->{baseName}.jar", @files);
unlink("chrome/$pkg->{baseName}.jar");

sub removeTimeLine
{
  my ($file, $line) = @_;

  return "\n" if $file =~ /\.jsm?$/ && $line =~ /\btimeLine\.(\w+)\(/;

  return $line;
}
