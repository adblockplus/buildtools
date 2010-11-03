#!/usr/bin/perl

use strict;
use warnings;
use lib qw(buildtools);
use Packager;

my $pkg = Packager->new();
$pkg->readMetadata('metadata');
$pkg->readLocales('chrome/locale');
$pkg->readLocaleData('chrome/locale');

foreach my $locale (sort {$a->{id} cmp $b->{id}} values %{$pkg->{localeData}})
{
  print "$locale->{id}\n$locale->{'name'}\n$locale->{'description.short'}\n$locale->{'description.long'}\n\n";
}
