# rdf/ -- the reference files as a graph (draft)

Renders the cdisc-for-ai reference files as RDF, so that every relationship the
Excel files carry implicitly -- shared key values, `;`-delimited lists, parallel
value/code lists, pipe-delimited keys -- is a declared, first-order statement.

Status: draft for discussion between Kerstin Forsberg and Dean Allemang. Built
from the committed reference files, so it runs without a cdisc.org sign-in and
inherits their pinned versions (recorded on `src:` nodes with each sheet's
content hash).

## Layout

| Path | What |
|---|---|
| `ontology/cfa.ttl` | The vocabulary. Each property has a sentence-rule label; the original properties also name the link kind they express (`cfa:linkKind`), from `link-semantics/docs/Link_Semantics.md`. |
| `ontology/cfa-mapping.ttl` | Every converter decision: source workbooks and sheets, IRI templates, which column feeds which property, list separators, spreadsheet tokens for individuals, run profiles. Change names and structure here. |
| `ontology/cfm.ttl` | The small vocabulary the mapping file is written in. |
| `src/build_rdf.py` | Generic engine; holds no CDISC names. |
| `src/run_queries.py` | Runs a `.rq` file against a Turtle file (loads `cfa.ttl` too). |
| `queries/glucose_walkthrough.rq` | The glucose walkthrough as SPARQL. |
| `queries/full_examples.rq` | Queries that cross the workbooks. |
| `output/glucose.ttl` | Profile `glucose`: GLUC + GLUCPE, 2 test codes, 8 DSSs. |
| `output/specimen_findings.ttl` | Profile `specimen`: all of Specimen_Findings. |
| `output/cdisc_for_ai.ttl` | Profile `full`: all twelve `machine_actionable` workbooks, about 623,000 triples. |

```
python3 rdf/src/build_rdf.py                    # glucose
python3 rdf/src/build_rdf.py --profile specimen # Specimen_Findings
python3 rdf/src/build_rdf.py --profile full     # everything
```

Requires `pip install rdflib pandas openpyxl`. The full build takes about a
minute. `resources/` (local NCIt downloads) is ignored by git.

## What the full profile reads

All twelve `machine_actionable` workbooks: SDTM_Test_Identity,
SDTM_Instrument_Test_Identity, SDTM_Instrument_Identity, the four Findings files,
Codelist_Phrases, Domain_Coverage, SDTM_Domain_Metadata, SDTM_Variables and
SDTMIG_Statements. Not `interim/`, `reports/` or the frozen `pre-2026-03/`
baselines.

Not read, because they copy another sheet that is read: each Findings file's
`Test_Identity` (except the NCIt parents in Immunogenicity's), `Axis_Meaning`
(copies `Variable_Meaning`) and `Domain_Variables` (copies `SDTM_Variables`);
SDTMIG_Statements' `Variables` sheet.

Not read, because the graph states them already: counts and rollups such as
`DSS_Count`, `DS_Codes`, `BC_IDs`, `Key_Positions`, `Key_Shared_With`,
`referenced_by`, `token_count`, `terms_in_codelist`, `TESTCD_Count`, `Distance`;
the yes/no consumer flags in `Domains` (the consumer is stated through
`Domain_Coverage`); `IG_Role_Differs_From_Model`; `in_dss_scope`.

## Modelling rules

1. **CDISC artifacts get their own IRIs; NCIt concepts keep NCIt's.** A test
   code, BC, DSS, codelist, instrument or variable is a node in our namespace
   and points to its NCIt concept with `cfa:isIdentifiedBy` (the identity link
   kind). NCIt IRIs are typed `cfa:NCItConcept`, a subclass of `skos:Concept`,
   never `owl:Class`.
2. **Mnemonics are scoped.** Test codes and DS codes are not identifiers, so
   their IRIs are domain + code (`tc:LB-GLUC`, `dss:LB-GLUCSER`). Variables are
   dataset + name (`var:LB-LBSPEC`), because STUDYID, USUBJID and the like occur
   in every dataset. Model variables are observation class + name
   (`mvar:Findings---SPEC`).
3. **One node per (DSS, variable).** A variable constraint
   (`cfa:VariableSpecialization`) replaces the `*_value / *_ncit / *_codelist /
   *_value_list / *_value_list_ncit` column families: `cfa:pinnedValue`,
   `cfa:permittedValue` (one triple per value), `cfa:drawsFrom` the codelist.
4. **Submission values live on codelist memberships**, not on concepts. So do
   CDISC's synonyms (`skos:altLabel` on the membership); NCIt's synonyms sit on
   the NCIt concept.
5. **The observable is a node.** `Observable_Key` becomes a `cfa:Observable`
   with component, component detail, system, method and scale. DSSs that share
   a key `cfa:realizes` the same node. A facet the DSS does not fix is stated
   as `cfa:leavesOpen`; a facet that is not part of the key in that domain as
   `cfa:doesNotKeyOn`. Only Specimen and Immunogenicity publish keys.
6. **Positions stay positions.** Facet position, kind, status, basis and
   evidence source from `Variable_Meaning` sit on the variable node, so
   published facts and Kerstin Forsberg's positions remain distinguishable.
7. **Copies merge.** The same codelist, term, test code or BC appearing in
   several workbooks becomes one node.

Namespace `https://w3id.org/cdisc-for-ai/` is a placeholder (not registered).

## Naming

Properties carry sentence-rule labels (`rdfs:label` in `cfa.ttl`): subject,
label, object should read as a sentence. Instance labels are set in the
mapping. Load `cfa.ttl` together with the output to see them in a viewer.

## Decisions for review (full conversion, 2026-11-20)

Made without discussion while extending from glucose to all workbooks; each
can be changed in `cfa-mapping.ttl` / `cfa.ttl`.

- **Variable IRIs now include the dataset** (`var:LBSPEC` became
  `var:LB-LBSPEC`), also in the glucose output.
- **Profile `all` is renamed `specimen`**; `full` is new.
- **New value lists are things, not strings**: observation class, variable role,
  core designation, data type, statement selection, phrase field, string source,
  sharing basis, coverage status, fold evidence, BC type, match method, key
  source, override type. Each is a class under `skos:Concept`, each value an
  individual `val:<list>-<value>` with the string as label and notation. The
  older strings (`bcCategory`, `resultScale`, `positionStatus`, `positionBasis`)
  are unchanged, as agreed.
- **Instruments are nodes** (`inst:<codelist>`), identified by the instrument's
  NCIt concept; `lists its questions in` the test-code codelist; `groups its
  questions under` the question-container concept.
- **Instrument test codes use the same IRI scheme** as domain-level ones
  (`tc:<domain>-<TESTCD>`): none collides with a domain-level code.
- **BC-to-BC parents** (instrument BCs) are `cfa:isGroupedUnder`, kept apart
  from `cfa:bcParent`, which points at an NCIt concept.
- **NCI's hierarchy** from Immunogenicity's Test_Identity and Test_Ancestors is
  `skos:broader` / `skos:broaderTransitive` between NCIt concepts; Model
  variables' NCIt parents likewise.
- **'scale' in Variable_Meaning** (no domain) is a `cfa:DerivedFacet`
  (`fct:scale`), not a variable.
- **Generic Model variables named in IG statements** (`--SPEC`) resolve to the
  Model variable of the statement domain's observation class, else to the
  General Observations one (`cfa:namesModelVariable`).
- **Phrases and collisions** get occurrence nodes, because their attributes
  (field, source, as published) belong to one phrase-term pair, not to the
  phrase.
- **Shared strings**: one node per (codelist, string), one use node per term,
  because the source (CT or NCIt) varies by term.
- **A submission value given without a codelist** becomes an NCIt concept's
  `skos:altLabel`, not its `skos:prefLabel` (one case: `s`, which would
  otherwise have relabelled C42535 "Second").
- **The four example test codes** of the instruments (`lzzt_example`, no NCIt
  code) get test-code nodes from the Findings file, without identity.

## Findings in the data

Found while converting; worth checking with Kerstin.

- COSMoS writes the DSS source variable as `LB.LBTESTCD`, but as `MB-MBTESTCD`
  in four MB DSSs.
- SAR2AB and TPLAB (MB) are used by DSSs but are not in SDTM_Test_Identity.
- Four PP test codes (AUCIFOUB, AUCIFPUB, AUCLSTUB, CMAXUB) occur only in
  Folded_Facets.
- 101 codelists cited by the SDTMIG variable tables are in no Codelists sheet,
  so the graph knows only their NCIt code.
- The NCIt concepts of codelists have no preferred term in the workbooks (the
  codelist name is CDISC's, not necessarily NCIt's), so they are unlabelled.

## Open questions

- `--STRESU` has no row in `Variable_Meaning`, so its variable carries no position.
- Should the observable be keyed on the BC at all, or on component + facets only?
- Test-code codelists (LBTESTCD etc.) are not in the Codelists sheets, so test
  codes are not yet linked to a codelist membership.
- Notebook form: the repo's convention is notebooks as processing logic; this
  is a script for fast iteration and can be wrapped as a notebook.
