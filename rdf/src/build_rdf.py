"""Build RDF from the cdisc-for-ai reference files, driven by the mapping.

The engine knows no CDISC names: classes, properties, IRI patterns, source
workbooks, sheets and columns, list separators and token lookups are all
declared in rdf/ontology/cfa-mapping.ttl (vocabulary: cfm.ttl), against the
vocabulary in rdf/ontology/cfa.ttl.

    python3 rdf/src/build_rdf.py                    # profile "glucose"
    python3 rdf/src/build_rdf.py --profile specimen # all of Specimen_Findings
    python3 rdf/src/build_rdf.py --profile full     # every reference file

Fail fast: a missing variable, an unknown token, a value that breaks a
cfm:valuePattern, parallel lists of unequal length, or an unmatched reference
stops the build.
"""
import argparse
import re
from collections import defaultdict
from pathlib import Path

import pandas as pd
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import RDF, RDFS, SKOS, XSD

REPO = Path(__file__).resolve().parents[2]
ONTOLOGY_DIR = REPO / "rdf/ontology"
CFM = Namespace("https://w3id.org/cdisc-for-ai/mapping-vocab#")
VAR = re.compile(r"\{(\w+)\}")
TRUE = Literal(True)


def safe(s):
    return re.sub(r"[^A-Za-z0-9._-]", "_", s)


def split(s, sep):
    return [p.strip() for p in s.split(sep) if p.strip()] if s else []


class Engine:
    def __init__(self):
        m = Graph()
        for f in ("cfm.ttl", "cfa.ttl", "cfa-mapping.ttl"):
            m.parse(ONTOLOGY_DIR / f)
        self.m = m
        self.prefixes = {p: str(ns) for p, ns in Graph().parse(ONTOLOGY_DIR / "cfa-mapping.ttl").namespaces()}
        self.out = Graph(bind_namespaces="none")
        for p, ns in self.prefixes.items():
            if p not in ("cfm", "map", ""):
                self.out.bind(p, ns)
        self.refs = defaultdict(set)
        self.sheets = {}
        self.rows_done = defaultdict(int)
        self._one, self._many, self._tokens = {}, {}, {}
        self.include = None      # files a scoped profile may read (None = all)

    # ------------------------------------------------------------ mapping access (memoized)
    def one(self, s, p, default=None):
        key = (s, p)
        if key not in self._one:
            self._one[key] = self.m.value(s, CFM[p])
        v = self._one[key]
        return default if v is None else v

    def text(self, s, p, default=""):
        v = self.one(s, p)
        return default if v is None else str(v)

    def many(self, s, p):
        key = (s, p)
        if key not in self._many:
            self._many[key] = list(self.m.objects(s, CFM[p]))
        return self._many[key]

    def flag(self, s, p):
        return self.one(s, p) == TRUE

    # ------------------------------------------------------------ helpers
    def sheet(self, file_node, sheet):
        key = (file_node, sheet)
        if key not in self.sheets:
            path = self.text(file_node, "path")
            df = pd.read_excel(REPO / path, sheet_name=sheet, dtype=str).fillna("")
            df["__file"] = path
            self.sheets[key] = df
        return self.sheets[key]

    def sheets_of(self, files, sheet):
        frames = [self.sheet(f, sheet) for f in files]
        return frames[0] if len(frames) == 1 else pd.concat(frames, ignore_index=True).fillna("")

    def fill(self, template, ctx, iri):
        def sub(mo):
            name = mo.group(1)
            if name not in ctx:
                raise KeyError(f"template {template!r}: no variable {name!r}")
            v = ctx[name]
            if iri:
                if v == "":
                    raise ValueError(f"template {template!r}: variable {name!r} is empty")
                return safe(v)
            return v
        return VAR.sub(sub, template)

    def expand(self, curie):
        prefix, _, rest = curie.partition(":")
        if prefix in self.prefixes and not rest.startswith("//"):
            return URIRef(self.prefixes[prefix] + rest)
        return URIRef(curie)

    def iri(self, template, ctx):
        return self.expand(self.fill(template, ctx, iri=True))

    def tokens(self, scheme):
        if scheme not in self._tokens:
            out = {}
            for ind, tok in self.m.subject_objects(CFM.sourceToken):
                if (ind, RDF.type, scheme) in self.m or (ind, CFM.inTokenScheme, scheme) in self.m:
                    out[str(tok)] = ind
            self._tokens[scheme] = out
        return self._tokens[scheme]

    # ------------------------------------------------------------ derived variables
    def derive(self, steps, ctx):
        for st in sorted(steps, key=lambda s: int(self.one(s, "order", 0))):
            name = self.text(st, "as")
            src = ctx[self.text(st, "fromVar")] if self.one(st, "fromVar") is not None else "x"
            if self.one(st, "splitParts") is not None:
                parts = src.split(self.text(st, "splitParts"))
                names = self.text(st, "partNames").split()
                expect = self.one(st, "expectParts")
                if expect is not None and len(parts) != int(expect):
                    raise ValueError(f"{name}: expected {expect} parts in {src!r}")
                for n, p in zip(names, parts):
                    ctx[f"{name}_{n}"] = p
            elif self.one(st, "splitOn") is not None or self.one(st, "findAll") is not None:
                if self.one(st, "splitOn") is not None:
                    items = src.split(self.text(st, "splitOn")) if src else []
                else:
                    items = re.findall(self.text(st, "findAll"), src)
                i = int(self.one(st, "pick"))
                ctx[name] = items[i].strip() if -len(items) <= i < len(items) else ""
            elif self.one(st, "replaceFrom") is not None:
                ctx[name] = src.replace(self.text(st, "replaceFrom"), self.text(st, "replaceTo"))
            elif self.one(st, "lookupSheet") is not None:
                key = ("lookup", st)
                if key not in self.sheets:
                    df = self.sheets_of(self.many(st, "lookupFile"), self.text(st, "lookupSheet"))
                    if self.one(st, "lookupKeyTemplate") is not None:
                        kt, vc = self.text(st, "lookupKeyTemplate"), self.text(st, "valueColumn")
                        table = {}
                        for r in df.to_dict("records"):
                            rr = dict(r, **{re.sub(r"\W", "_", k): v for k, v in r.items()})
                            table.setdefault(self.fill(kt, rr, iri=False), r[vc])
                        self.sheets[key] = table
                    else:
                        self.sheets[key] = dict(zip(df[self.text(st, "keyColumn")], df[self.text(st, "valueColumn")]))
                table = self.sheets[key]
                keys = [src] if self.one(st, "keyTemplate") is None else \
                    [self.fill(self.text(st, "keyTemplate"), ctx, iri=False)] + \
                    [self.fill(str(t), ctx, iri=False) for t in self.many(st, "fallbackKeyTemplate")]
                hit = next((table[k] for k in keys if k in table), None)
                if hit is None and src and not self.flag(st, "optional"):
                    raise KeyError(f"{name}: {keys} not found in {self.text(st, 'lookupSheet')}")
                ctx[name] = hit or ""
            else:
                raise ValueError(f"derive step {st} has no operation")

    # ------------------------------------------------------------ property maps
    def conditions_hold(self, pm, ctx):
        if any(not ctx.get(str(c), "") for c in self.many(pm, "onlyIfPresent")):
            return False
        if any(ctx.get(str(c), "") for c in self.many(pm, "onlyIfEmpty")):
            return False
        col = self.one(pm, "onlyIfColumn")
        if col is not None:
            v = ctx.get(str(col), "")
            if self.one(pm, "inValues") is not None and v not in self.text(pm, "inValues").split():
                return False
            if self.one(pm, "matches") is not None and not re.fullmatch(self.text(pm, "matches"), v):
                return False
        return True

    def emit(self, pm, subj, ctx):
        if not self.conditions_hold(pm, ctx):
            return
        pred = self.one(pm, "predicate")
        on_subject = self.one(pm, "onSubject")
        const = self.one(pm, "objectConstant")
        if const is not None:
            self.out.add((self.iri(str(on_subject), ctx) if on_subject is not None else subj, pred, const))
            return
        col = self.one(pm, "column")
        if col is not None:
            raw = ctx.get(str(col), "")
            sep = self.one(pm, "split")
            values = split(raw, str(sep)) if sep is not None else ([raw] if raw else [])
            pcol = self.one(pm, "pairedColumn")
            if pcol is not None:
                pairs_raw = ctx.get(str(pcol), "")
                psep = self.one(pm, "pairedSplit")
                pv = split(pairs_raw, str(psep)) if psep is not None else [pairs_raw]
                if values and len(values) != len(pv):
                    raise ValueError(f"{col} vs {pcol}: {len(values)} values vs {len(pv)} in row {ctx.get('__row__', '?')}")
                pairs = list(zip(values, pv))
            else:
                pairs = [(v, "") for v in values]
        else:
            pairs = [("", "")]
        tok_scheme = self.one(pm, "tokensFrom")
        toks = self.tokens(tok_scheme) if tok_scheme is not None else {}
        prefix_len = self.one(pm, "bindPrefix")
        for v, pair in pairs:
            c2 = dict(ctx, value=v, pair=pair)
            if prefix_len is not None:
                c2["value_prefix"] = v[:int(prefix_len)]
            s_ = self.iri(str(on_subject), c2) if on_subject is not None else subj
            skip = self.one(pm, "skipUnlessPattern")
            if skip is not None and not re.fullmatch(str(skip), v):
                continue
            if v in toks:
                obj = toks[v]
            elif tok_scheme is not None and self.one(pm, "objectTemplate") is None:
                raise KeyError(f"token {v!r} not in {tok_scheme}")
            elif self.one(pm, "objectTemplate") is not None:
                pat = self.one(pm, "valuePattern")
                if pat is not None and col is not None and not re.fullmatch(str(pat), v):
                    raise ValueError(f"{col}: {v!r} does not match {pat}")
                obj = self.iri(self.text(pm, "objectTemplate"), c2)
                ocls = self.one(pm, "objectClass")
                if ocls is not None:
                    self.out.add((obj, RDF.type, ocls))
                olab = self.one(pm, "objectLabel")
                if olab is not None:
                    self.out.add((obj, RDFS.label, Literal(self.fill(str(olab), c2, iri=False))))
                onot = self.one(pm, "objectNotation")
                if onot is not None:
                    self.out.add((obj, SKOS.notation, Literal(self.fill(str(onot), c2, iri=False))))
            elif self.one(pm, "literalTemplate") is not None:
                obj = Literal(self.fill(self.text(pm, "literalTemplate"), c2, iri=False))
            else:
                dt = self.one(pm, "datatype")
                if dt == XSD.boolean:
                    obj = Literal(v == self.text(pm, "trueToken"), datatype=XSD.boolean)
                elif dt is not None:
                    obj = Literal(v, datatype=dt)
                else:
                    obj = Literal(v)
            self.out.add((s_, pred, obj))
            for ref in self.many(pm, "recordsReference"):
                key_t = self.text(ref, "keyTemplate")
                if all(c2.get(n, "") for n in VAR.findall(key_t)):
                    self.refs[self.text(ref, "referenceSet")].add(self.fill(key_t, c2, iri=False))

    # ------------------------------------------------------------ row mappings
    def contexts(self, mp, df, row):
        base = dict(row, __row__=str(row))
        for k in row:
            alias = re.sub(r"\W", "_", k)
            if alias != k:
                base.setdefault(alias, row[k])
        path = row["__file"]
        base.update(file_path=path, file_name=Path(path).name, file_stem=Path(path).stem)
        fe = self.one(mp, "forEachSplit")
        fam = self.one(mp, "forEachFamily")
        if fe is not None:
            for part in split(base[self.text(fe, "column")], self.text(fe, "split")):
                yield dict(base, **{self.text(fe, "as"): part})
        elif fam is not None:
            rx = re.compile(str(fam))
            families = sorted({rx.match(c).group(1) for c in df.columns if rx.match(c)})
            need = [str(x) for x in self.many(mp, "requireAny")]
            suffixes = self.text(mp, "familySuffixes").split()
            for F in families:
                ctx = dict(base, FAMILY=F)
                for suf in suffixes:
                    ctx[f"f_{suf}"] = base.get(f"{F}_{suf}", "")
                if need and not any(ctx[n] for n in need):
                    continue
                yield ctx
        else:
            yield base

    def run_mapping(self, mp, scope):
        if scope is not None and self.flag(mp, "onlyUnscoped"):
            return
        files = self.many(mp, "sourceFile")
        if self.include is not None:
            files = [f for f in files if f in self.include]
        if not files:
            return
        df = self.sheets_of(files, self.text(mp, "sourceSheet"))
        scol = self.one(mp, "scopeColumn")
        if scol is not None and scope is not None:
            df = df[df[str(scol)].isin(scope[self.text(mp, "scopeSet")])]
        restrict = self.one(mp, "restrictTo")
        if restrict is not None and scope is not None:
            rset, key_t = self.text(restrict, "referenceSet"), self.text(restrict, "keyTemplate")
            keys = df.apply(lambda r: self.fill(key_t, dict(r), iri=False), axis=1) if len(df) else pd.Series([], dtype=str)
            missing = self.refs[rset] - set(keys)
            if missing:
                raise KeyError(f"{mp}: references not found in sheet: {sorted(missing)[:5]}")
            df = df[keys.isin(self.refs[rset])]
        subject_t, cls = self.text(mp, "subject"), self.one(mp, "class")
        pms, steps = self.many(mp, "property"), self.many(mp, "derive")
        checks = [(self.text(c, "column"), self.text(c, "matches")) for c in self.many(mp, "requireMatch")]
        need = [str(x) for x in self.many(mp, "skipRowUnless")]
        avoid = [str(x) for x in self.many(mp, "skipRowIf")]
        for row in df.to_dict("records"):
            for ctx in self.contexts(mp, df, row):
                # filters on columns run before derived variables are computed
                if need and not all(ctx.get(n, "") for n in need if n in ctx):
                    continue
                if avoid and any(ctx.get(n, "") for n in avoid if n in ctx):
                    continue
                self.derive(steps, ctx)
                if need and not all(ctx.get(n, "") for n in need):
                    continue
                if avoid and any(ctx.get(n, "") for n in avoid):
                    continue
                for col, rx in checks:
                    if not re.fullmatch(rx, ctx[col]):
                        raise ValueError(f"{mp}: {col}={ctx[col]!r} does not match {rx}")
                subj = self.iri(subject_t, ctx)
                if cls is not None:
                    self.out.add((subj, RDF.type, cls))
                for pm in pms:
                    self.emit(pm, subj, ctx)
            self.rows_done[mp] += 1

    # ------------------------------------------------------------ profiles
    def scope(self, profile):
        if self.flag(profile, "unscoped"):
            return None
        testcds = set(self.text(profile, "testCodes").split())
        for src in self.many(profile, "testCodesFrom"):
            df = self.sheet(self.one(src, "sourceFile"), self.text(src, "sourceSheet"))
            testcds |= set(df[self.text(src, "column")])
        domains = set()
        for src in self.many(profile, "domainsFrom"):
            df = self.sheet(self.one(src, "sourceFile"), self.text(src, "sourceSheet"))
            domains |= set(df[df[self.text(src, "filterColumn")].isin(testcds)][self.text(src, "column")])
        return {"testcd": testcds, "domain": domains}

    def build(self, profile_name):
        profiles = [p for p in self.m.subjects(RDF.type, CFM.RunProfile) if self.text(p, "name") == profile_name]
        if len(profiles) != 1:
            raise KeyError(f"profile {profile_name!r} not found (or not unique)")
        profile = profiles[0]
        inc = self.many(profile, "includeFile")
        self.include = set(inc) if inc else None
        scope = self.scope(profile)
        mappings = sorted(self.m.subjects(RDF.type, CFM.RowMapping),
                          key=lambda mp: (int(self.one(mp, "phase", 1)), str(mp)))
        for mp in mappings:
            self.run_mapping(mp, scope)
        out = REPO / self.text(profile, "output")
        self.out.serialize(out, format="turtle")
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="glucose", help="cfm:name of a cfm:RunProfile in cfa-mapping.ttl")
    a = ap.parse_args()
    e = Engine()
    out = e.build(a.profile)
    for mp, n in sorted(e.rows_done.items(), key=lambda kv: str(kv[0])):
        print(f"  {str(mp).rsplit('#', 1)[-1]:<28} {n:>6} rows")
    print(f"{len(e.out)} triples -> {out.relative_to(REPO)}")


if __name__ == "__main__":
    main()
