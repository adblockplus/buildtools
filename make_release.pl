#!/usr/bin/perl

#############################################################################
# This is the release automation script, it will change current extension   #
# version, create release builds and commit it all into Mercurial. Usually  #
# you just want to create a build - use make_devbuild.pl for this.          #
#############################################################################

use strict;
use lib qw(buildtools);
use Packager;

my $pkg = Packager->new({locales => ['en-US']});
$pkg->readMetadata('metadata');
$pkg->readLocaleData('chrome/locale');
die "Could not extract extension name" unless $pkg->{name};

die "Branch name not defined in metadata file" unless exists($pkg->{settings}{general}{branchname});

my $baseName = $pkg->{settings}{general}{basename};
my $extensionName = $pkg->{name};

die "Version number not specified" unless @ARGV;

my $version = $ARGV[0];
$version =~ s/[^\w\.]//gs;

my $branch = $version;
$branch =~ s/\./_/g;
$branch = $pkg->{settings}{general}{branchname}."_".$branch."_RELEASE";

open(local *OLD, '<', 'metadata');
open(local *NEW, '>', 'metadata_new');
binmode(OLD);
binmode(NEW);
while (<OLD>)
{
  s/^(\s*version\s*=\s*).*/$1$ARGV[0]/;
  print NEW $_;
}
close(NEW);
close(OLD);
unlink('metadata');
rename('metadata_new', 'metadata');

system(qq(hg commit -m "Releasing $extensionName $version"));
system(qq(hg tag -f $branch));
system(qq(hg tag -R ../buildtools -f $branch));

@ARGV = ("../downloads/$baseName-$version.xpi");
do 'buildtools/create_xpi.pl';
die $@ if $@;

system('hg', 'archive', '-X', '.hgtags', 'tmp');
system('hg', 'archive', '-R', 'buildtools', '-X', 'buildtools/.hgtags', 'tmp/buildtools');

opendir(local *TMP, 'tmp');
system('tar', 'czf', "../downloads/$baseName-$version-source.tgz", '--directory=tmp', '--numeric-owner', grep {/[^.]/} readdir(TMP));
closedir(TMP);
$pkg->rm_rec('tmp');

system("hg add -R ../downloads ../downloads/$baseName-$version.xpi");
system("hg add -R ../downloads ../downloads/$baseName-$version-source.tgz");
system(qq(hg commit -R ../downloads -m "Releasing $extensionName $version"));
system(qq(hg tag -R ../downloads -f $branch));

system(qq(hg push));
system(qq(hg push -R ../downloads));
system(qq(hg push -R ../buildtools));
