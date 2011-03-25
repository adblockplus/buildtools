package Packager;

use strict;
use warnings;

my %apps =
(
  conkeror => '{a79fe89b-6662-4ff4-8e88-09950ad4dfde}',
  emusic => 'dlm@emusic.com',
  fennec => '{a23983c0-fd0e-11dc-95ff-0800200c9a66}',
  firefox => '{ec8030f7-c20a-464f-9b0e-13a3a9e97384}',
  midbrowser => '{aa5ca914-c309-495d-91cf-3141bbb04115}',
  prism => 'prism@developer.mozilla.org',
  seamonkey => '{92650c4d-4b8e-4d2a-b7eb-24ecf4f6b63a}',
  songbird => 'songbird@songbirdnest.com',
  thunderbird => '{3550f703-e582-4d05-9a08-453d09bdfdc6}',
  toolkit => 'toolkit@mozilla.org',
);

sub new
{
  my ($class, $params) = @_;

  unless (exists($params->{build}))
  {
    $params->{build} = `hg id -i`;
    $params->{build} =~ s/\W//gs;
  }

  my $self = bless($params, $class);

  return $self;
}

sub readMetadata
{
  my ($self, $metadataFile) = @_;

  my $data = $self->readFile($metadataFile);
  die "Could not read metadata file $metadataFile" unless defined $data;

  $self->{settings} = {};
  my $curSection;
  my %lists = map {$_ => 1} qw(contributor);
  foreach my $line (split(/[\r\n]+/, $data))
  {
    $line =~ s/#.*//;
    $line =~ s/^\s+//;
    $line =~ s/\s+$//;
    next unless length($line);

    if ($line =~ /^\[(.*)\]$/)
    {
      $curSection = $1;
    }
    elsif ($line =~ /(.+)=(.*)/)
    {
      if (defined $curSection)
      {
        $self->{settings}{$curSection} = {} unless exists $self->{settings}{$curSection};
        if (exists($lists{$1}))
        {
          $self->{settings}{$curSection}{$1} = [] unless exists $self->{settings}{$curSection}{$1};
          push @{$self->{settings}{$curSection}{$1}}, $2;
        }
        else
        {
          $self->{settings}{$curSection}{$1} = $2;
        }
      }
      else
      {
        warn "Setting outside section in metadata file: $line";
      }
    }
    else
    {
      warn "Unrecognized line in metadata file: $line";
    }
  }

  warn "Version not set in metadata file" unless exists($self->{settings}{general}{version});
  $self->{version} = $self->{settings}{general}{version};
  if (exists $self->{devbuild})
  {
    $self->{version} .= "." . $self->{devbuild};
  }
}

sub readLocales
{
  my ($self, $localesDir, $includeIncomplete) = @_;

  opendir(local *DIR, $localesDir) or die "Could not open locales directory $localesDir";
  my @locales = grep {!/[^\w\-]/ && ($includeIncomplete || !-e("$localesDir/$_/.incomplete"))} readdir(DIR);
  closedir(DIR);
  
  @locales = sort {$a eq "en-US" ? -1 : ($b eq "en-US" ? 1 : $a cmp $b)} @locales;

  $self->{locales} = \@locales;
}

sub readLocaleData
{
  my ($self, $localesDir) = @_;

  $self->{localeData} = {};
  $self->{name} = '';
  $self->{description} = '';
  $self->{homepage} = '';
  $self->{author} = '';

  foreach my $locale (@{$self->{locales}})
  {
    my $data = $self->readFile("$localesDir/$locale/meta.properties");
    next unless defined $data;

    $self->{localeData}{$locale} = {id => $locale};
    while ($data =~ /^\s*(?![!#])(\S+)\s*=\s*(.+)$/mg)
    {
      if ($1 eq "name" || $1 eq "description" || $1 eq "homepage" || $1 eq "translator" || $1 eq "description.short" || $1 eq "description.long")
      {
        $self->{localeData}{$locale}{$1} = $2;
      }
    }
  }

  if (exists($self->{localeData}{"en-US"}))
  {
    $self->{name} = $self->{localeData}{"en-US"}{name} if exists($self->{localeData}{"en-US"}{name});
    $self->{description} = $self->{localeData}{"en-US"}{description} if exists($self->{localeData}{"en-US"}{description});
  }
  $self->{homepage} = $self->{settings}{homepage}{default};
  $self->{author} = $self->{settings}{general}{author};

  # Fix up locale data if missing
  foreach my $locale (values %{$self->{localeData}})
  {
    $locale->{name} = $self->{name} unless exists($locale->{name}) && $locale->{name};
    $locale->{description} = $self->{description} unless exists($locale->{description}) && $locale->{description};

    if (exists($self->{settings}{homepage}{$locale->{id}}))
    {
      $locale->{homepage} = $self->{settings}{homepage}{$locale->{id}};
    }
    elsif ($locale->{id} =~ /^(\w+)/ && exists($self->{settings}{homepage}{$1}))
    {
      $locale->{homepage} = $self->{settings}{homepage}{$1};
    }
    else
    {
      $locale->{homepage} = $self->{settings}{homepage}{default};
    }
    warn "Failed to get homepage for $locale->{id}" unless $locale->{homepage};
  }
}

sub rm_rec
{
  my ($self, $dir) = @_;

  opendir(local *DIR, $dir) or return;
  foreach my $file (readdir(DIR))
  {
    if ($file =~ /[^.]/)
    {
      if (-d "$dir/$file")
      {
        $self->rm_rec("$dir/$file");
      }
      else
      {
        unlink("$dir/$file");
      }
    }
  }
  closedir(DIR);

  rmdir($dir);
}

sub cp
{
  my ($self, $fromFile, $toFile, $exclude) = @_;

  if ($exclude)
  {
    foreach my $file (@$exclude)
    {
      return if index($fromFile, $file) >= 0;
    }
  }

  my $textMode = ($fromFile =~ /\.(manifest|xul|jsm?|xml|xhtml|rdf|dtd|properties|css)$/);
  my $extendedTextMode = ($fromFile =~ /\.(?:jsm?|rdf|manifest)$/);

  open(local *FROM, $fromFile) or return;
  open(local *TO, ">$toFile") or return;
  binmode(TO);
  if ($textMode)
  {
    print TO map {
      s/\r//g;
      s/^((?:  )+)/"\t" x (length($1)\/2)/e;
      s/\{\{VERSION\}\}/$self->{version}/g if $extendedTextMode;
      s/\{\{BUILD\}\}/$self->{build}/g if $extendedTextMode;
      if ($extendedTextMode && /\{\{LOCALE\}\}/)
      {
        my $loc = "";
        for my $locale (@{$self->{locales}})
        {
          my $tmp = $_;
          $tmp =~ s/\{\{LOCALE\}\}/$locale/g;
          $loc .= $tmp;
        }
        $_ = $loc;
      }

      $_ = $self->{postprocess_line}->($fromFile, $_) if exists $self->{postprocess_line};

      $_;
    } <FROM>;
  }
  else
  {
    local $/;
    binmode(FROM);
    print TO <FROM>;
  }

  $self->{postprocess_file}->($fromFile, *TO) if exists $self->{postprocess_file};

  close(TO);
  close(FROM);
}

sub cp_rec
{
  my ($self, $fromDir, $toDir, $exclude) = @_;

  if ($exclude)
  {
    foreach my $file (@$exclude)
    {
      return if index($fromDir, $file) >= 0;
    }
  }

  my @files;
  if ($fromDir =~ /\blocale$/ && exists $self->{locales})
  {
    @files = @{$self->{locales}};
  }
  else
  {
    opendir(local *DIR, $fromDir) or return;
    @files = readdir(DIR);
    closedir(DIR);
  }

  $self->rm_rec($toDir);
  mkdir($toDir);
  foreach my $file (@files)
  {
    if ($file =~ /[^.]/)
    {
      if (-d "$fromDir/$file")
      {
        $self->cp_rec("$fromDir/$file", "$toDir/$file", $exclude);
      }
      else
      {
        $self->cp("$fromDir/$file", "$toDir/$file", $exclude);
      }
    }
  }
}

sub encodeXML
{
  my ($self, $str) = @_;
  $str =~ s/&/&amp;/g;
  $str =~ s/</&lt;/g;
  $str =~ s/>/&gt;/g;
  $str =~ s/"/&quot;/g; #"
  return $str;
}

sub createFileDir
{
  my ($self, $fileName) = @_;

  my @parts = split(/\/+/, $fileName);
  pop @parts;

  my $dir = '.';
  foreach my $part (@parts)
  {
    $dir .= '/' . $part;
    mkdir($dir);
  }
}

sub fixZipPermissions
{
  my ($self, $fileName) = @_;
  my $invalid = 0;
  my($buf, $entries, $dirlength);

  open(local *FILE, "+<", $fileName) or ($invalid = 1);
  unless ($invalid)
  {
    seek(FILE, -22, 2);
    sysread(FILE, $buf, 22);
    (my $signature, $entries, $dirlength) = unpack("Vx6vVx6", $buf);
    if ($signature != 0x06054b50)
    {
      print STDERR "Wrong end of central dir signature!\n";
      $invalid = 1;
    }
  }
  unless ($invalid)
  {
    seek(FILE, -22-$dirlength, 2);
    for (my $i = 0; $i < $entries; $i++)
    {
      sysread(FILE, $buf, 46);
      my ($signature, $namelen, $attributes) = unpack("Vx24vx8V", $buf);
      if ($signature != 0x02014b50)
      {
        print STDERR "Wrong central file header signature!\n";
        $invalid = 1;
        last;
      }
      my $attr_high = $attributes >> 16;
      $attr_high = ($attr_high & ~0777) | ($attr_high & 040000 ? 0755 : 0644);
      $attributes = ($attributes & 0xFFFF) | ($attr_high << 16);
      seek(FILE, -8, 1);
      syswrite(FILE, pack("V", $attributes));
      seek(FILE, 4 + $namelen, 1);
    }
  }
  close(FILE);

  unlink $fileName if $invalid;
}

sub writeManifest
{
  my ($self, $manifestFile) = @_;

  my $id = $self->encodeXML($self->{settings}{general}{id});
  my $version = $self->encodeXML($self->{version});
  my $name = $self->encodeXML($self->{name});
  my $description = $self->encodeXML($self->{description});
  my $author = $self->encodeXML($self->{author});
  my $homepage = $self->encodeXML($self->{homepage});

  open(local *FILE, '>', $manifestFile) or die "Failed to write manifest file $manifestFile";
  binmode(FILE);
  print FILE <<"EOT";
<?xml version="1.0"?>

<RDF xmlns="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
\t\txmlns:em="http://www.mozilla.org/2004/em-rdf#">

\t<Description about="urn:mozilla:install-manifest">

\t\t<em:id>$id</em:id>
\t\t<em:version>$version</em:version>
\t\t<em:name>$name</em:name>
\t\t<em:description>$description</em:description>
\t\t<em:creator>$author</em:creator>
\t\t<em:homepageURL>$homepage</em:homepageURL>
\t\t<em:type>2</em:type>
EOT

  my $updateURL;
  if ($self->{devbuild})
  {
    $updateURL = "https://adblockplus.org/devbuilds/$self->{settings}{general}{basename}/update.rdf";
  }
  elsif (exists($self->{settings}{general}{updateURL}))
  {
    $updateURL = $self->{settings}{general}{updateURL};
  }
  if (defined $updateURL)
  {
    $updateURL = $self->encodeXML($updateURL . '?reqVersion=%REQ_VERSION%&id=%ITEM_ID%&version=%ITEM_VERSION%&maxAppVersion=%ITEM_MAXAPPVERSION%&status=%ITEM_STATUS%&appID=%APP_ID%&appVersion=%APP_VERSION%&appOS=%APP_OS%&appABI=%APP_ABI%&locale=%APP_LOCALE%&currentAppVersion=%CURRENT_APP_VERSION%&updateType=%UPDATE_TYPE%');
    print FILE <<"EOT";
\t\t<em:updateURL>$updateURL</em:updateURL>
EOT
  }

  if (exists($self->{settings}{general}{icon}))
  {
    my $icon = $self->encodeXML($self->{settings}{general}{icon});
    print FILE <<"EOT";
\t\t<em:iconURL>$icon</em:iconURL>
EOT
  }
  if (exists($self->{settings}{general}{about}))
  {
    my $about = $self->encodeXML($self->{settings}{general}{about});
    print FILE <<"EOT";
\t\t<em:aboutURL>$about</em:aboutURL>
EOT
  }
  if (exists($self->{settings}{general}{options}))
  {
    my $options = $self->encodeXML($self->{settings}{general}{options});
    print FILE <<"EOT";
\t\t<em:optionsURL>$options</em:optionsURL> 
EOT
  }

  print FILE "\n";

  if (exists($self->{settings}{general}{contributor}))
  {
    foreach my $contributor (map {$self->encodeXML($_)} @{$self->{settings}{general}{contributor}})
    {
      print FILE <<"EOT";
\t\t<em:contributor>$contributor</em:contributor>
EOT
    }
    print FILE "\n";
  }

  my %translators = ();
  foreach my $locale (values %{$self->{localeData}})
  {
    if (exists($locale->{translator}))
    {
      foreach my $translator (split(/,/, $locale->{translator}))
      {
        $translator =~ s/^\s+//g;
        $translator =~ s/\s+$//g;
        $translators{$translator} = 1 if $translator ne "";
      }
    }
  }
  foreach my $translator (sort keys %translators)
  {
    $translator = $self->encodeXML($translator);
    print FILE <<"EOT";
\t\t<em:translator>$translator</em:translator>
EOT
  }
  print FILE "\n";

  foreach my $locale (sort {$a->{id} cmp $b->{id}} values %{$self->{localeData}})
  {
    my $id = $self->encodeXML($locale->{id});
    my $name = $self->encodeXML($locale->{name});
    my $description = $self->encodeXML($locale->{description});
    my $homepage = $self->encodeXML($locale->{homepage});

    # Duplicate author in each locale to work around bug 416350
    my $author = $self->encodeXML($self->{author});

    print FILE <<"EOT";
\t\t<em:localized>
\t\t\t<Description>
\t\t\t\t<em:locale>$id</em:locale>
\t\t\t\t<em:name>$name</em:name>
\t\t\t\t<em:description>$description</em:description>
\t\t\t\t<em:creator>$author</em:creator>
\t\t\t\t<em:homepageURL>$homepage</em:homepageURL>
\t\t\t</Description>
\t\t</em:localized>
EOT
  }
  print FILE "\n";

  foreach my $app (sort keys %{$self->{settings}{compat}})
  {
    if (!exists($apps{$app}))
    {
      warn "Unrecognized application in manifest: $app";
      next;
    }

    my $id = $self->encodeXML($apps{$app});
    my ($min, $max) = map {$self->encodeXML($_)} split(/\//, $self->{settings}{compat}{$app});

    print FILE <<"EOT";
\t\t<em:targetApplication>
\t\t\t<Description>
\t\t\t\t<!-- $app -->
\t\t\t\t<em:id>$id</em:id>
\t\t\t\t<em:minVersion>$min</em:minVersion>
\t\t\t\t<em:maxVersion>$max</em:maxVersion>
\t\t\t</Description>
\t\t</em:targetApplication>
EOT
  }

  print FILE <<"EOT";
\t</Description>  
</RDF>
EOT

  close(FILE);
}

sub makeJAR
{
  my ($self, $jarFile, @files) = @_;

  $self->rm_rec('tmp');
  unlink($jarFile);

  mkdir('tmp');

  my @include = ();
  my @exclude = ();
  foreach my $file (@files)
  {
    if ($file =~ s/^-//)
    {
      push @exclude, $file;
    }
    else
    {
      push @include, $file;
    }
  }

  foreach my $file (@include)
  {
    if (-d $file)
    {
      $self->cp_rec($file, "tmp/$file", \@exclude);
    }
    else
    {
      $self->cp($file, "tmp/$file", \@exclude);
    }
  }

  chdir('tmp');
  $self->fixLocales();
  system('zip', '-rqXD0', $jarFile, @include);
  chdir('..');

  rename("tmp/$jarFile", "$jarFile");
  
  $self->rm_rec('tmp');
}

sub fixLocales()
{
  my $self = shift;

  # Add missing files
  opendir(local *DIR, "locale/en-US") or return;
  foreach my $file (readdir(DIR))
  {
    next if $file =~ /^\./;

    foreach my $locale (@{$self->{locales}})
    {
      next if $locale eq "en-US";

      if (-f "locale/$locale/$file")
      {
        if ($file =~ /\.dtd$/)
        {
          $self->fixDTDFile("locale/$locale/$file", "locale/en-US/$file");
        }
        elsif ($file =~ /\.properties$/)
        {
          $self->fixPropertiesFile("locale/$locale/$file", "locale/en-US/$file");
        }
      }
      else
      {
        $self->cp("locale/en-US/$file", "locale/$locale/$file");
      }
    }
  }
  closedir(DIR);

  # Remove extra files
  foreach my $locale (@{$self->{locales}})
  {
    next if $locale eq "en-US";

    opendir(local *DIR, "locale/$locale") or next;
    foreach my $file (readdir(DIR))
    {
      next if $file =~ /^\./;

      unlink("locale/$locale/$file") unless -f "locale/en-US/$file";
    }
    closedir(DIR);
  }
}

my $S = qr/[\x20\x09\x0D\x0A]/;
my $Name = qr/[A-Za-z_:][\w.\-:]*/;
my $Reference = qr/&$Name;|&#\d+;|&#x[\da-fA-F]+;/;
my $PEReference = qr/%$Name;/;
my $EntityValue = qr/"(?:[^%&"]|$PEReference|$Reference)*"|'(?:[^%&']|$PEReference|$Reference)*'/;  #"

sub fixDTDFile
{
  my ($self, $file, $referenceFile) = @_;

  my $data = $self->readFile($file);
  my $reference = $self->readFile($referenceFile);

  my $changed = 0;
  $data .= "\n" unless $data =~ /\n$/s;
  while ($reference =~ /<!ENTITY$S+($Name)$S+$EntityValue$S*>/gs)
  {
    my ($match, $name) = ($&, $1);
    unless ($data =~ /<!ENTITY$S+$name$S+$EntityValue$S*>/s)
    {
      $data .= "$match\n";
      $changed = 1;
    }
  }

  $self->writeFile($file, $data) if $changed;
}

sub fixPropertiesFile
{
  my ($self, $file, $referenceFile) = @_;

  my $data = $self->readFile($file);
  my $reference = $self->readFile($referenceFile);

  my $changed = 0;
  $data .= "\n" unless $data =~ /\n$/s;
  while ($reference =~ /^\s*(?![!#])(\S+)\s*=\s*?.*$/mg)
  {
    my ($match, $name) = ($&, $1);
    unless ($data =~ /^\s*(?![!#])($name)\s*=\s*?.*$/m)
    {
      $data .= "$match\n";
      $changed = 1;
    }
  }

  $self->writeFile($file, $data) if $changed;
}

sub readFile
{
  my ($self, $file) = @_;

  open(local *FILE, "<", $file) || return undef;
  binmode(FILE);
  local $/;
  my $result = <FILE>;
  close(FILE);

  return $result;
}

sub writeFile
{
  my ($self, $file, $contents) = @_;

  open(local *FILE, ">", $file) || return;
  binmode(FILE);
  print FILE $contents;
  close(FILE);
}

sub makeXPI
{
  my ($self, $xpiFile, @files) = @_;

  $self->rm_rec('tmp');
  unlink($xpiFile);

  mkdir('tmp');

  foreach my $file (@files)
  {
    if (-d $file)
    {
      $self->cp_rec($file, "tmp/$file");
    }
    else
    {
      $self->createFileDir("tmp/$file");
      $self->cp($file, "tmp/$file");
    }
  }

  $self->writeManifest('tmp/install.rdf');
  push @files, 'install.rdf';

  if (-f '.signature')
  {
    my $signData = $self->readFile(".signature");
    my ($signtool) = ($signData =~ /^signtool=(.*)/mi);
    my ($certname) = ($signData =~ /^certname=(.*)/mi);
    my ($dbdir) = ($signData =~ /^dbdir=(.*)/mi);
    my ($dbpass) = ($signData =~ /^dbpass=(.*)/mi);

    system($signtool, '-k', $certname, '-d', $dbdir, '-p', $dbpass, 'tmp');

    # Add signature files to list and make sure zigbert.rsa is always compressed first
    opendir(local *METADIR, 'tmp/META-INF');
    unshift @files, map {"META-INF/$_"} sort {
      my $aValue = ($a eq 'zigbert.rsa' ? -1 : 0);
      my $bValue = ($b eq 'zigbert.rsa' ? -1 : 0);
      $aValue <=> $bValue;
    } grep {!/^\./} readdir(METADIR);
    closedir(METADIR);
  }

  chdir('tmp');
  system('zip', '-rqDX9', '../temp_xpi_file.xpi', @files);
  chdir('..');

  $self->fixZipPermissions("temp_xpi_file.xpi") if $^O =~ /Win32/i;
  
  rename("temp_xpi_file.xpi", $xpiFile);

  $self->rm_rec('tmp');
}

1;
