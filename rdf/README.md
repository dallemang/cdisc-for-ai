# rdf/ -- the reference files as a graph (draft)

First pass at rendering the cdisc-for-ai reference files as RDF, so that every
relationship the Excel files carry implicitly -- shared key values,
`;`-delimited lists, parallel value/code lists, pipe-delimited keys -- is a
declared, first-order statement.

Status: draft for discussion between Kerstin Forsberg and Dean Allemang. Built
from the committed reference files, so it runs without a cdisc.org sign-in and
inherits their pinned versions (recorded on `src:` nodes with each sheet's
content hash).

## Layout

| Path | What |
|---|---|
| `ontology/cfa.ttl` | The vocabulary. Each property names the link kind it expresses (`cfa:linkKind`), from `link-semantics/docs/Link_Semantics.md`. |
| `ontology/cfa-mapping.ttl` | Every converter decision: source sheets, IRI templates, which column feeds which property, list separators, spreadsheet tokens for individuals, run profiles. Change names and structure here. |
| `ontology/cfm.ttl` | The small vocabulary the mapping file is written in. |
| `src/build_rdf.py` | Generic engine; holds no CDISC names. `python3 rdf/src/build_rdf.py` builds the glucose profile; `--profile all` builds all of Specimen_Findings. |
| `src/run_queries.py` | Runs a `.rq` file against a Turtle file. |
| `queries/glucose_walkthrough.rq` | The glucose walkthrough as SPARQL. |
| `output/glucose.ttl` | GLUC + GLUCPE: 2 test codes, 8 DSSs. |
| `output/specimen_findings.ttl` | All 169 DSSs of Specimen_Findings. |

Requires `pip install rdflib pandas openpyxl`.

## Modelling rules

1. **CDISC artifacts get their own IRIs; NCIt concepts keep NCIt's.** A test
   code, BC, DSS, codelist or variable is a node in our namespace and points to
   its NCIt concept with `cfa:isIdentifiedBy` (the identity link kind). NCIt IRIs are never typed with our
   classes.
2. **Mnemonics are scoped.** Test codes and DS codes are not identifiers, so
   their IRIs are domain + code (`tc:LB-GLUC`, `dss:LB-GLUCSER`).
3. **One node per (DSS, variable).** A variable constraint (`cfa:VariableSpecialization`) replaces the
   `*_value / *_ncit / *_codelist / *_value_list / *_value_list_ncit` column
   families: `cfa:pinnedValue`, `cfa:permittedValue` (one triple per value),
   `cfa:drawsFrom` the codelist.
4. **Submission values live on codelist memberships**, not on concepts.
5. **The observable is a node.** `Observable_Key` becomes a `cfa:Observable`
   with component, component detail, system, method and scale. DSSs that share
   a key `cfa:realizes` the same node. A facet the DSS does not fix is stated
   as `cfa:leavesOpen` (e.g. leaves open method); a facet that is not part of
   the key in that domain as `cfa:doesNotKeyOn` (e.g. MB does not key on
   system). The objects are the facet individuals `cfa:System`, `cfa:Method`,
   `cfa:ComponentDetail`, so no placeholder values sit in object positions.
6. **Positions stay positions.** Facet position, kind, status and basis from
   `Axis_Meaning` sit on the variable node, so published facts and our
   positions remain distinguishable.

Namespace `https://w3id.org/cdisc-for-ai/` is a placeholder (not registered).

## Naming

Properties carry sentence-rule labels (`rdfs:label` in `cfa.ttl`): subject,
label, object should read as a sentence. Instance labels are set in the
mapping. Load `cfa.ttl` together with the output to see them in a viewer.

## Open questions

- `--STRESU` has no row in `Axis_Meaning`, so its variable carries no position.
- Should the observable be keyed on the BC at all, or on component + facets only?
- Test-code codelists (LBTESTCD etc.) are not in the Codelists sheet, so test
  codes are not yet linked to a codelist membership.
- Notebook form: the repo's convention is notebooks as processing logic; this
  is a script for fast iteration and can be wrapped as a notebook.
