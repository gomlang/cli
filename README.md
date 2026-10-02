# ecosystem::cli

Command-line parsing with explicit command schemas, typed conversion, subcommands
and three third-party compile-time derives. Argument parsing is deterministic by
default; process arguments and environment lookup are explicit entry points.

```goml
use ecosystem::cli;
use cli::{Args, ArgValue};

#[derive(ArgValue)]
enum Mode { Fast, Safe }

#[derive(Args)]
#[command(name = "serve", about = "Serve files", version = "1.0")]
struct Options {
    #[arg(short = "p", default = "8080", env = "PORT")]
    port: u16,
    #[arg(default = "safe")]
    mode: Mode,
    #[arg(short = "v", count)]
    verbose: isize,
    #[arg(positional)]
    files: Vec[string],
}

fn options(arguments: Vec[string]) -> Result[Options, cli::Error] {
    cli::parse(arguments)
}
```

## Explicit schemas

Build a schema with `Command::new`, `about`, `version`, `arg`, `subcommand` and
`require_subcommand`. `Argument::new` consumes a value, `Argument::flag` records a
boolean switch, and `Argument::counter` counts occurrences. The free functions
`command`, `argument`, `flag` and `counter` provide equivalent constructors.

Argument builders include `short`, `help`, `required`, `multiple`, `positional`,
`default_value`, `env`, `possible_values`, `conflicts_with`, `requires`, `alias`
and `global`. `Command.alias` adds a subcommand spelling; matches always use
canonical command/argument names. Aliases collide with canonical names and other
aliases during schema validation, and cannot use reserved option names.
Positional indices are contiguous from zero; a repeated positional must be last.
Required positionals precede optional positionals. Commands and arguments are
public records; `validate` checks the schema, including duplicate names/short
options, invalid positions and unknown conflict/dependency targets.

`Command::parse` takes arguments without the executable name. Supported forms
include `--name value`, `--name=value`, `-p80`, `-p 80`, short-flag clusters such
as `-vvq`, and `--` to terminate option processing. Values beginning with `--`
must use the equals form. Use `--` for positional values beginning with `-`.
Scalar duplicates are rejected; repeated values preserve input order. Flags do
not accept explicit values. `--help`/`-h` and `--version`/`-V` are reserved.

Subcommands have their own schemas. Ordinary parent options precede the
subcommand. Options marked `global(true)` can occur before or after any nested
subcommand and appear in every descendant's help. Values and occurrence counts
are available at their declaring command and each selected descendant through
`Matches::subcommand`. Repeated values preserve order across levels; scalar
duplicates still fail. Defaults/environment are evaluated after explicit input,
and constraints are enforced at the declaring command. A child cannot shadow an
inherited name, alias or short option. Global positionals are invalid. `--` stops
option and subcommand recognition at the current level. Schema depth is capped at 64.

`Command.group(ArgGroup::new(name, members))` defines a group of canonical argument
names, allowing at most one distinct member by default. `required(true)` requires
exactly one, while `bounds(minimum, maximum)` supports other cardinalities.
Explicit arguments and environment values participate; defaults do not. Multiple
occurrences of one argument count once. Groups may overlap but cannot contain
unknown/duplicate members or invalid bounds. Help displays aliases, inherited
options and group constraints.

## Values and environment

`Matches` provides `raw`, `value[T]`, `optional[T]`, `values[T]`, `flag`, `count`,
`contains` and `was_provided`. Typed getters use `ArgValue`; standard
implementations cover strings, booleans, all integer widths and f32/f64.
Integer conversions enforce destination bounds. Applications may implement
`ArgValue` for custom types.

Precedence is explicit arguments, then environment, then defaults.
`parse_with_env` accepts an injected lookup function, making tests independent
of the host environment. `parse_env` reads process arguments (skipping argv[0])
and environment variables. Generic `cli::parse`, `cli::parse_with_env` and
`cli::parse_env` additionally decode an `Args` type.

Environment values count as provided for conflict/dependency checks; defaults do
not. A requirement may be satisfied by a default. Flags and counters do not take
environment values, defaults or choice lists. Repeated value arguments receive a
single value from an environment variable; automatic separator splitting is not
performed.

## Derives

`#[derive(Args)]` supports structs, including generic structs. Plain fields are
required unless they have a default, booleans become optional flags, `Option[T]`
is optional, and `Vec[T]` is repeated. A count field must be `isize`. Derived
bounds apply `ArgValue` to the actual scalar or container-element type.

`#[command(...)]` accepts string `name`, `about`, `version`, and `alias`. `#[arg(...)]`
accepts switches `positional`, `required`, `optional`, `multiple`, `count`, and `global`,
and string values `long`, `short`, `help`, `default`, `env`, `choices`, `conflicts`
`requires` and `alias`. `choices`, `conflicts` and `requires` use `|`-separated
names/values; `alias` supplies one additional long option spelling. Empty string
defaults are preserved. Field underscores become hyphens in default option
names. Positional indices follow field order, including flattened fields.
Unknown attributes and incompatible mode switches produce compile-time
diagnostics. Explicit `optional` and `multiple` switches require `Option[T]`
and `Vec[T]`, respectively.
Attribute values accept ordinary escaped strings and raw strings (`r"..."` or
hash-delimited forms). Raw text is preserved, including backslashes and empty
defaults. Non-string named values and duplicate keys within one attribute are
diagnosed rather than silently ignored.

`#[arg(flatten)]` embeds another `Args` struct at the same command level. The
nested struct is decoded from the same matches; its arguments, argument groups
and subcommands are merged into the parent schema. Requiredness, defaults,
environment values, aliases, global options, conflicts and dependencies retain
their usual behavior. Positionals are offset by the parent's preceding
positionals. The parent keeps its command name, description, version and aliases.
Multiple flatten fields and multiple levels of flattening are supported, including
generic structs and manually implemented `Args`. Flattened fields must be an
`Args` type, not `Option[T]` or `Vec[T]`, and cannot carry other argument attributes.
Name/short-option collisions, group conflicts, invalid positional ordering and
global-option shadowing remain recoverable `InvalidSchema` errors.

`#[derive(Subcommands)]` supports nonempty enums with unit variants and variants
containing exactly one `Args` value. Variant names default to ASCII lowercase with
underscores replaced by hyphens. Variants accept string
`#[command(name = "serve", alias = "s", about = "Serve files", version = "2")]`.
Names and aliases must be unique, valid command spellings. The variant controls
the command name and aliases; its payload's description and version are inherited
unless overridden on the variant. Named-field variants and multi-value tuple
variants should use a separate derived `Args` struct as their single payload.

```goml
use ecosystem::cli;
use cli::{Args, Subcommands};

#[derive(Args)]
struct Common {
    #[arg(short = "v", count, global)]
    verbose: isize,
}

#[derive(Args)]
struct Serve {
    #[arg(default = "8080", env = "PORT")]
    port: u16,
}

#[derive(Subcommands)]
enum Action {
    #[command(alias = "s", about = "Serve files")]
    Serve(Serve),
    Status,
}

#[derive(Args)]
#[command(name = "app")]
struct Application {
    #[arg(flatten)]
    common: Common,
    #[arg(subcommand)]
    action: Action,
}
```

`#[arg(subcommand)]` requires a selected command for a plain `Subcommands` field;
`Option[SubcommandsType]` permits no command and decodes it as `None`.
`#[arg(subcommand, required)]` also supports an `Option` field when absence should
be an error. Selected commands decode their typed payload and any nested selector
in that payload. Ordinary option attributes do not apply to selectors. Each
command level supports one selector, including those brought in through
flattening; multiple direct selectors are rejected at compile time and multiple
flattened selectors return `InvalidSchema` before parsing. Put further
selectors inside subcommand payloads to create additional command levels.
Help/version handling and inherited globals work at every level.

`subcommands_for::[Action]()` exposes the enum's command list through a
`TypedCommand[Action]`. `decode_subcommand` and `decode_optional_subcommand` decode
the selected child of existing `Matches`; `Subcommands::from_subcommand` takes the
child itself. `decode_args` decodes an `Args` value from existing matches. These
entry points support manually implemented traits as well as derives.
`Command.flatten` provides the same schema merge for explicit builders;
`positional_count` reports how many positional slots are present. `Command.named`
replaces the canonical name and clears aliases for reuse as a different command.
`flatten_args` additionally rejects merging independent subcommand selectors;
ordinary `flatten` can combine explicit subcommand lists. `composition_errors`
retains derived schema errors through further composition, and `validate`/`parse`
report them as `InvalidSchema`. Builder-based schemas and `TypedCommand` remain
compatible. Code constructing a complete `Command` record directly must add
`composition_errors: Vec::new()` or use `..Command::new(name)` for default fields.

`#[derive(ArgValue)]` supports nonempty enums with unit variants. Variant names
default to ASCII lowercase with underscores replaced by hyphens. A variant may
have `#[value(name = "plain-text", alias = "text")]`. Duplicate wire names and
payload variants are rejected. All derives support imported aliases and use
definition-site helper identities, so caller names such as `Command` do not
capture generated references.

`schema::[Options]()` returns an ordinary `Command` for validation, help and
composition. Its generic argument selects the derived schema even though the
returned command has no type parameter. Generic forwarding and first-class
schema function values work across dependencies with GoML 0.1.50.
`command_for::[Options]()` and the `Args::schema` trait method retain their
`TypedCommand[Options]` result for compatibility; its `command` field exposes
the same schema.

## Shell completion

`Command.completion_script(Shell::Bash | Shell::Zsh | Shell::Fish)` validates the
schema and returns a standalone completion script. It writes no files and does
not modify shell configuration. Derived `Args` use the same API:

```goml
let script = cli::schema::[Options]().completion_script(cli::Shell::Bash)?;
```

Scripts support nested subcommands and aliases, inherited global options,
long-option aliases, short flags and clusters, `--option=value`, attached short
values such as `-mfast`, positional choices and a final repeated positional.
An option awaiting a value completes its `possible_values` only, including when
the previous word is a short cluster such as `-vvm`. Words consumed as option
values do not select subcommands. `--` disables options and subcommands at the
current command level; positional choices remain available. `--help` and the
version options are offered where the parser supports them. Root command aliases
register the same completion function for each executable spelling.

Completion offers static schema candidates, not a second validation pass. It
does not suppress already-used scalar options or enforce groups, conflicts,
required arguments or valid values in earlier words. Free-form arguments without
`possible_values` have no value candidates. There are no dynamic callbacks,
filesystem candidates or type-based suggestions; derived fields can declare
`#[arg(choices = "fast|safe")]` explicitly. Schema descriptions are not included
in completion output. Generation returns `InvalidSchema` for invalid schemas or
choices containing NUL, newline, carriage return or tab, which cannot be carried
consistently by the shells' line-oriented candidate interfaces. Spaces, quotes,
backslashes and shell metacharacters in choices remain literal text. Generated
scripts do not use `eval` or execute schema strings.

Requires Bash 4+, Zsh 5+, or Fish 3.4+. With the `examples/completions` schema
(named `app`), generate and load a script explicitly:

```sh
goml run --example completions -- bash > app.bash
source ./app.bash
```

For persistent Bash use, source that file from your own shell startup file. For
Zsh, initialize completion before sourcing the generated script:

```sh
goml run --example completions -- zsh > app.zsh
autoload -Uz compinit
compinit
source ./app.zsh
```

For Fish, install the generated file in its standard per-user completion path:

```sh
mkdir -p ~/.config/fish/completions
goml run --example completions -- fish > ~/.config/fish/completions/app.fish
```

Use the application's executable name as its schema name and completion filename.
Regenerate scripts after changing the schema. Applications may expose generation
through their own command or installer; the library does not reserve a completion
subcommand or invoke a shell automatically. Real Bash, Zsh and Fish tests cover
candidate selection and escaping. They require all three executables on `PATH`;
`GOML_CLI_TEST_FISH` can select a Fish executable explicitly.

## Errors and validation

`Error` distinguishes `Help`, `Version`, `Usage`, `InvalidValue` and
`InvalidSchema`, with a printable message. Help and version requests return
before required-value checks. The library never exits the process or prints on
the caller's behalf.

```sh
(cd ../verification && just ecosystem-test cli)
```

Tests exercise explicit schemas, clusters, terminators, duplicate/missing values,
environment precedence, conflicts, subcommands, generated generic decoding,
custom conversion, enum aliases, empty defaults, integer overflow and stable
help text. Composition regressions cover nested generic payloads, required and
optional selectors, flattened positional offsets and argument groups, global
options at multiple command levels, alias canonicalization, help/version
inheritance and invalid schemas. The `examples/parse` example and its downstream verification check
exported derives, import aliases and generated-name hygiene;
A GoML test checks 33 invalid derives through temporary downstream modules, using `std::process` to assert compiler exit status and precise diagnostics.

Flag/counter defaults and environment values remain future work. Schemas must
form a finite command tree; recursive type definitions that would expand into an
infinite command tree are unsupported.

## Development and examples

Requires GoML 0.1.56 or newer. The `examples/parse/` and `examples/completions/`
examples share the root manifest. From the library root, run:

```sh
goml run --example parse
goml test
goml verify --timeout 300s
```

`goml test` builds the example and runs its tests. `goml verify` repeats the example checks as an independent module against an isolated registry snapshot. `(cd ../verification && just ecosystem-test cli)` also retains the library-specific smoke and compatibility checks.
