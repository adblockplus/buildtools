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
$pkg->readMetadata('metadata');
$pkg->readLocales('chrome/locale', 1);
$pkg->readLocaleData('chrome/locale');

$pkg->{localeData} = {};

foreach my $app (keys %{$pkg->{settings}{compat}})
{
  delete $pkg->{settings}{compat}{$app} unless $app eq 'firefox' || $app eq 'thunderbird' || $app eq 'seamonkey'
}

my $baseName = $pkg->{settings}{general}{basename};
my $version = $pkg->{version};
my $xpiFile = "$baseName-$version.xpi";

chdir('chrome');
$pkg->makeJAR("$baseName.jar", 'content', 'skin', 'locale', '-/tests', '-/mochitest', '-/.incomplete');
chdir('..');

my @files = grep {-e $_} ('components', <modules/*.jsm>, 'defaults', 'bootstrap.js', 'chrome.manifest', 'icon.png');

$pkg->makeXPI($xpiFile, "chrome/$baseName.jar", @files);
unlink("chrome/$baseName.jar");
