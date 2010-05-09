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
$params{version} = shift @ARGV;
die "Please specify version number on command line" unless $params{version};

my $pkg = Packager->new(\%params);
$pkg->readBasename('chrome.manifest');
$pkg->readLocales('chrome/locale', 1);
$pkg->readLocaleData('chrome/locale');

my $baseName = $pkg->{baseName};
my $xpiFile = "$baseName-$params{version}.xpi";

chdir('chrome');
$pkg->makeJAR("$baseName.jar", 'content', 'skin', 'locale', '-/tests', '-/mochitest', '-/.incomplete');
chdir('..');

my @files = grep {-e $_} ('components', 'modules', 'defaults', 'install.rdf', 'bootstrap.js', 'chrome.manifest', 'icon.png');

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

  return $line;
}
