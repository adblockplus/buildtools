#!/usr/bin/perl

#############################################################################
# This script will create a special development build meant only for upload #
# to Babelzilla.                                                            #
#############################################################################

use strict;
use warnings;
use lib qw(buildtools);
use Packager;

sub Packager::fixLocales() {}

my %params = ();

my ($sec, $min, $hour, $day, $mon, $year) = localtime;
$params{devbuild} = sprintf("%04i%02i%02i", $year+1900, $mon+1, $day);

my $pkg = Packager->new(\%params);
$pkg->readBasename('chrome.manifest');
$pkg->readVersion('version');
$pkg->readLocales('chrome/locale', 1);
$pkg->readLocaleData('chrome/locale', 'install.rdf');

my $baseName = $pkg->{baseName};
my $version = $pkg->{version};
my $xpiFile = "$baseName-$version.xpi";

chdir('chrome');
$pkg->makeJAR("$baseName.jar", 'content', 'skin', 'locale', '-/tests', '-/mochitest', '-/.incomplete');
chdir('..');

my @files = grep {-e $_} ('components', <modules/*.jsm>, 'defaults', 'install.rdf', 'bootstrap.js', 'chrome.manifest', 'icon.png');

my $targetAppNum = 0;
$pkg->{postprocess_line} = \&postprocessInstallRDF;
$pkg->makeXPI($xpiFile, "chrome/$baseName.jar", @files);
unlink("chrome/$baseName.jar");

sub postprocessInstallRDF
{
  my ($file, $line) = @_;

  return $line unless $file eq "install.rdf";

  if ($line =~ /\btargetApplication\b/)
  {
    $targetAppNum++;
    return "" if $targetAppNum > 6;
  }

  return "" if $targetAppNum > 6 && $targetAppNum % 2 == 1;

  return "" if $line =~ /\blocalized\b/;

  return $line;
}
