#!/usr/bin/perl

#############################################################################
# This is the release automation script, it will change current extension   #
# version, create release builds and commit it all into Mercurial. Usually  #
# you just want to create a build - use make_devbuild.pl for this.          #
#############################################################################

use strict;
use lib qw(buildtools);
use Packager;

our $BRANCH_NAME;

die "This script cannot be called directly, please call the script for a particular extension" unless $BRANCH_NAME;

my $pkg = Packager->new({locales => ['en-US']});
$pkg->readBasename('chrome.manifest');
$pkg->readLocaleData('chrome/locale', 'install.rdf');
$pkg->readNameFromManifest('install.rdf') unless $pkg->{name};
die "Could not extract extension name" unless $pkg->{name};

my $baseName = $pkg->{baseName};
my $extensionName = $pkg->{name};

die "Version number not specified" unless @ARGV;

my $version = $ARGV[0];
$version =~ s/[^\w\.]//gs;

open(VERSION, ">version");
print VERSION $ARGV[0];
close(VERSION);

@ARGV = ("../downloads/$baseName-$version.xpi");
do 'buildtools/create_xpi.pl';
die $@ if $@;

system("hg add -R ../downloads ../downloads/$baseName-$version.xpi");
system(qq(hg commit -m "Releasing $extensionName $version"));
system(qq(hg commit -R ../downloads -m "Releasing $extensionName $version"));

my $branch = $version;
$branch =~ s/\./_/g;
$branch = $BRANCH_NAME."_".$branch."_RELEASE";
system(qq(hg tag $branch));
system(qq(hg tag -R ../downloads $branch));
system(qq(hg tag -R ../buildtools $branch));

system(qq(hg push));
system(qq(hg push -R ../downloads));
system(qq(hg push -R ../buildtools));
