#!/usr/bin/perl

#############################################################################
# This is the release automation script, it will change current extension   #
# version, create release builds and commit it all into Mercurial. Usually  #
# you just want to create a build - use make_devbuild.pl for this.          #
#############################################################################

use strict;
use Cwd;

our $BRANCH_NAME;

die "This script cannot be called directly, please call the script for a particular extension" unless $BRANCH_NAME;

my $manifest = readFile("chrome.manifest");
unless ($manifest =~ /\bjar:chrome\/(\S+?)\.jar\b/)
{
  die "Could not find JAR file name in chrome.manifest";
}
my $baseName = $1;

my $installRDF = readFile("install.rdf");
$installRDF =~ s/<em:(requires|targetApplication)>.*?<\/em:\1>//gs;
unless ($installRDF =~ /<em:name>\s*([^<>]+?)\s*<\/em:name>/)
{
  die "Could not find extension name in install.rdf";
}
my $extensionName = $1;

die "Version number not specified" unless @ARGV;

my $version = $ARGV[0];
$version =~ s/[^\w\.]//gs;

open(VERSION, ">version");
print VERSION $ARGV[0];
close(VERSION);

@ARGV = ("../downloads/$baseName-$version.xpi");
do '../create_xpi.pl';

die "Failed to determine current directory name" unless cwd() =~ /([^\\\/]+)[\\\/]?$/;
my $dir = $1;

chdir('..');
system("hg add downloads/$baseName-$version.xpi");
system(qq(hg commit -m "Releasing $extensionName $version" downloads $dir));

my $branch = $version;
$branch =~ s/\./_/g;
$branch = $BRANCH_NAME."_".$branch."_RELEASE";
system(qq(hg tag $branch));

#system(qq(hg push));

sub readFile
{
  my $file = shift;

  open(local *FILE, "<", $file) || die "Could not read file '$file'";
  binmode(FILE);
  local $/;
  my $result = <FILE>;
  close(FILE);

  return $result;
}
