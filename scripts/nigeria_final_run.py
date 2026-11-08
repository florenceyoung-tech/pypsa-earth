#!/usr/bin/env python3
"""Prepare and check a separate cost revision without replacing the existing study.

Run with the project's activated conda environment. No model solve is automatic.
"""
import argparse
import ast
import copy
import csv
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import subprocess
import sys

ALLOWED_RULES = ['process_cost_data', 'add_electricity', 'simplify_network',
                 'cluster_network', 'add_extra_components', 'prepare_network',
                 'add_co2_constraint', 'solve_network', 'solve_all_networks']
CACHE_SETTINGS = ['countries', 'snapshots', 'atlite', 'renewable', 'conventional',
                  'clustering', 'base_network', 'load_options', 'lines', 'electricity']

REVISION = 'nigeria_final_v1'
OLD_DIR = Path('configs/nigeria_study')
NEW_DIR = Path('configs') / REVISION
DATA_DIR = Path('data/nigeria_study/final_v1')
SOURCE_HASH = '289166e9b1acb1c92eb2732bc8761b7c4ee11cee68feaae22d89bebbb7f3a4a8'
MMBTU_MWH = 0.29307107
CPI_2024 = 313.689
F_2025 = CPI_2024 / 321.943
F_LAZARD = CPI_2024 / 333.918  # July 2026 proxy for July publication
F_GAS = CPI_2024 / 333.952  # June 2026 regulatory assumption
ENERGY_SHARE = .722  # Explicit author allocation; exact NREL share NOT verified
BESS_2025 = 140.4522568601


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + '\n')


def merged(a, b):
    a = copy.deepcopy(a)
    for k, v in b.items():
        a[k] = merged(a[k], v) if isinstance(v, dict) and isinstance(a.get(k), dict) else copy.deepcopy(v)
    return a


def safe(root, relative):
    p = Path(relative)
    if p.is_absolute() or '..' in p.parts:
        raise ValueError(f'Unsafe relative path: {relative}')
    dest = root / p
    for q in [dest, *dest.parents]:
        if q == root:
            break
        if q.is_symlink():
            raise ValueError(f'Refusing symlink: {q}')
    return dest


def assumptions():
    return {
        'revision': REVISION, 'target_currency': 'USD', 'target_price_year': 2024,
        'cpi_series': 'BLS CUUR0000SA0 CPI-U US city average all items not seasonally adjusted',
        'cpi_url': 'https://www.bls.gov/regions/northeast/data/consumerpriceindex_us_table.htm',
        'cpi_values': {'2024_annual': CPI_2024, '2025_annual': 321.943,
                       '2026_June': 333.952, '2026_July': 333.918},
        'factors': {'IRENA_2025_to_2024': F_2025, 'Lazard_July2026_proxy_to_2024': F_LAZARD,
                    'NERC_June2026_to_2024': F_GAS},
        'gas_quote': {'value': 3.39, 'unit': 'USD/MMBtu', 'period': 'June 2026',
                      'scope': 'gas supply and transportation regulatory tariff assumption, not all project contracts',
                      'source': 'NERC ORDER/NERC/2026/091 Table 1 p4',
                      'url': 'https://nerc.gov.ng/wp-content/uploads/2026/07/IE_MYTO_JUNE_2026.pdf'},
        'battery': {'benchmark_2025_usd_per_kwh': BESS_2025, 'benchmark_duration_h': 4,
                    'energy_share': ENERGY_SHARE, 'power_share': 1-ENERGY_SHARE,
                    'split_status': 'author assumption; NREL supports method but exact shares unverified',
                    'model_duration_h': 6, 'energy_life_y': 15, 'power_life_y': 20,
                    'FOM_fraction_each_component': .02, 'explicit_augmentation': False},
        'retained_efficiencies_HHV': {'CCGT': .53, 'OCGT': .37},
        'scope': 'Historical benchmark costs held constant across finance cases; no technology learning forecast',
        'final_decisions': {
            'unserved_energy': 'Load shedding disabled in final expansion cases; physical supply must satisfy nodal balances',
            'matched_cap_sweep': 'Add 8.8 Mt capped counterparts at renewable nominal WACC 7, 11, 17 and 20 percent; D2 supplies 13.79 percent point; gas held at 14.68 percent',
            'cached_inputs': 'Reuse only cost-independent B2 base network, plant list, demand, shapes, base bus regions and renewable profiles; rebuild all cost-dependent networks',
            'new_gas_availability': 'Keep 1.0 reference and 0.85 sensitivity; constant hourly derating, not annual capacity factor',
            'hydro': 'Retain EIA2023 normalisation and multiplier 1.268 without a second calibration factor',
            'co2_cap_status': 'Analytical allocation; 12.4 Mt grid baseline remains unverified; not an official sectoral target',
        },
    }


def cache_inventory(root, configs):
    """Check reusable physical inputs before writing any new study files."""
    import yaml
    base = yaml.safe_load((root/'config.default.yaml').read_text())
    original = json.loads((root/OLD_DIR/'manifest.json').read_text())
    source = next(e for e in original if e['scenario']=='B2')
    source_cfg = yaml.safe_load((root/source['config']).read_text())
    if sha(root/source['config']) != source['config_sha256']:
        raise ValueError('B2 source configuration differs from its manifest.')
    merged_source = merged(base, source_cfg)
    source_run = source_cfg['run']['name']
    for e,cfg in configs:
        c=merged(base,cfg)
        for key in CACHE_SETTINGS:
            if c.get(key)!=merged_source.get(key):
                raise ValueError(f"{e['scenario']}: {key} differs from B2. Cannot reuse that physical cache without review.")
    files = [('networks', 'base.nc'), ('resources','powerplants.csv'),
             ('resources','demand_profiles.csv'),
             ('resources','shapes/country_shapes.geojson'),
             ('resources','shapes/gadm_shapes.geojson'),
             ('resources','bus_regions/regions_onshore.geojson'),
             ('resources','bus_regions/regions_offshore.geojson')]
    for tech in source_cfg['renewable']:
        if tech in source_cfg['electricity']['renewable_carriers']:
            files.append(('resources',f'renewable_profiles/profile_{tech}.nc'))
    # Additional shape inputs can be required by configured subregions.
    shape_dir=root/'resources'/source_run/'shapes'
    if shape_dir.is_dir():
        for p in sorted(shape_dir.rglob('*')):
            if p.is_file():
                item=('resources','shapes/'+str(p.relative_to(shape_dir)))
                if item not in files:files.append(item)
    missing=[];record=[]
    for area,relative in files:
        p=safe(root,Path(area)/source_run/relative)
        if not p.is_file():missing.append(str(p.relative_to(root)))
        else:record.append({'area':area,'relative':relative,'source':str(p.relative_to(root)),
                            'sha256':sha(p),'size_bytes':p.stat().st_size})
    for rel in ['data/hydro_capacities.csv','data/nuclear_p_max_pu.csv',
                merged_source['electricity']['agg_p_nom_limits']['file']]:
        if not safe(root,rel).is_file():missing.append(rel)
    if missing:
        raise ValueError('Reusable inputs missing; no download attempted:\n  '+'\n  '.join(missing))
    return {'source_run':source_run,'source_config':source['config'],
            'source_config_sha256':source['config_sha256'],'files':record,
            'allowed_rules':ALLOWED_RULES,'policy':'Frozen inputs are referenced by symlinks; their producers are excluded from the DAG'}


def stage_cache(root, rows):
    """Link frozen files only; never link any downstream network or costs."""
    rec=json.loads((root/DATA_DIR/'cache_inputs.json').read_text())
    if sha(root/rec['source_config'])!=rec['source_config_sha256']:
        raise ValueError('The cached B2 configuration changed after preparation.')
    pairs=[]
    for f in rec['files']:
        src=safe(root,f['source'])
        if not src.is_file() or sha(src)!=f['sha256']:
            raise ValueError(f"Reusable input changed: {f['source']}")
        for e in rows:
            dest=root/f['area']/e['run_name']/f['relative']
            # Refuse symlink parent directories, but permit the exact frozen file link.
            safe(root,dest.parent.relative_to(root))
            if dest.is_symlink():
                if dest.resolve()!=src.resolve():raise ValueError(f'Unexpected cache link: {dest}')
            elif dest.exists():
                if not dest.is_file() or sha(dest)!=f['sha256']:
                    raise ValueError(f'Different file already exists at cache destination: {dest}')
            else:pairs.append((src,dest))
    for src,dest in pairs:
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.symlink_to(os.path.relpath(src,dest.parent))
    print(f'REUSED_B2_PHYSICAL_INPUTS {len(rec["files"])} source files; upstream rules disabled',flush=True)


def checked_command(config, cores, dry_run=False, has_cap=True):
    allowed=[r for r in ALLOWED_RULES if has_cap or r!='add_co2_constraint']
    cmd=['snakemake','--cores',str(cores),'solve_all_networks','--configfile',config,
         '--rerun-incomplete','--latency-wait','60','--allowed-rules',*allowed]
    if dry_run:cmd.append('--dry-run')
    return cmd


def revised_rows(path):
    with Path(path).open(newline='') as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)
    replacements = {
        ('solar', 'investment'): (837*F_2025, 'IRENA 2026 Table 3.1 companion workbook G6 Africa 2025',
             '837 USD2025/kW_DC x BLS CPI 313.689/321.943; PV nominal capacity uses panel rating basis'),
        ('solar-utility', 'investment'): (837*F_2025, 'IRENA 2026 Table 3.1 companion workbook G6 Africa 2025',
             '837 USD2025/kW_DC x BLS CPI 313.689/321.943; same as solar'),
        ('onwind', 'investment'): (1550*F_2025, 'IRENA 2026 Table 2.1 companion workbook G9 Africa 2025',
             '1550 USD2025/kW x BLS CPI 313.689/321.943'),
        ('battery storage', 'investment'): (BESS_2025*F_2025*ENERGY_SHARE,
             'IRENA 2026 Fig 9.2 workbook S6; author energy allocation',
             '140.4522568601 USD2025/kWh usable x CPI 313.689/321.943 x 0.722; split is author assumption, not verified NREL statistic'),
        ('battery inverter', 'investment'): (BESS_2025*F_2025*(1-ENERGY_SHARE)*4,
             'IRENA 2026 Fig 9.2 workbook S6; author power allocation',
             'Four-hour total x CPI 313.689/321.943 x 0.278 x 4; power-related cost includes allocated BOS, not inverter hardware alone'),
        ('CCGT', 'investment'): (2100*F_LAZARD, 'Lazard July 2026 LCOE+ v19 p28 upper CCGT benchmark',
             '2100 x CPI 313.689/333.918; July index is a dated proxy, not observed full-year 2026 inflation; not a Nigeria project quote'),
        ('OCGT', 'investment'): (1650*F_LAZARD, 'Lazard July 2026 LCOE+ v19 p28 upper gas peaking benchmark',
             '1650 x CPI 313.689/333.918; generic peaker CAPEX paired with explicit modern OCGT efficiency proxy'),
        ('CCGT', 'VOM'): (5*F_LAZARD, 'Lazard July 2026 LCOE+ v19 p28 upper CCGT VOM',
             '5 USD2026/MWh_e x CPI 313.689/333.918'),
        ('OCGT', 'VOM'): (5*F_LAZARD, 'Lazard July 2026 LCOE+ v19 p28 upper gas peaking VOM',
             '5 USD2026/MWh_e x CPI 313.689/333.918'),
        ('gas', 'fuel'): (3.39*F_GAS/MMBTU_MWH, 'NERC ORDER/NERC/2026/091 June 2026 Table 1 p4',
             '3.39 USD/MMBtu includes supply and transport; x CPI 313.689/333.952 / 0.29307107 MWh/MMBtu; thermal HHV convention'),
    }
    seen = set()
    for r in rows:
        key = (r['technology'], r['parameter'])
        if key in replacements:
            val, source, desc = replacements[key]
            r.update(value=format(val, '.14g'), source=source,
                     **{'further description': desc, 'currency_year': '2024'})
            seen.add(key)
        if r['technology'] in {'battery storage', 'battery inverter'} and r['parameter'] == 'FOM':
            r.update(source='Author-selected 2 percent of component CAPEX per year informed by Lazard 2026 p38',
                     **{'further description': 'Not a unique Lazard midpoint; no explicit augmentation, warranty or cycling degradation cost'})
        if r['parameter'] == 'discount rate':
            r.update(source='Legacy source-only financing value overridden by study scenario',
                     **{'further description': 'Do not treat as real WACC; effective discount rates are in scenario costs.discountrate_groups'})
        if key == ('CCGT', 'efficiency'):
            r.update(source='Author assumption 0.53 HHV', **{'further description':
                'Approximate modern benchmark informed by Lazard; NOT exact heat-rate midpoint; applied uniformly existing and new'})
        if key == ('OCGT', 'efficiency'):
            r.update(source='Author assumption 0.37 HHV modern aeroderivative proxy', **{'further description':
                'GE 0.41 LHV x assumed LHV/HHV ratio 0.90 approximately 0.369; NOT Lazard peaker midpoint; uniform existing and new'})
    if seen != set(replacements):
        raise ValueError(f'Missing source rows: {set(replacements)-seen}')
    return fields, rows


def prepare(root):
    import yaml
    old_manifest = safe(root, OLD_DIR/'manifest.json')
    entries = json.loads(old_manifest.read_text())
    selected = [x for x in entries if x['scenario'] not in {'B3', 'D3'}]
    configs, sources = [], set()
    for e in selected:
        p = safe(root, e['config'])
        if sha(p) != e['config_sha256']:
            raise ValueError(f'{p} differs from its manifest. Regenerate the existing manifest or share current files before preparing.')
        cfg = yaml.safe_load(p.read_text())
        sources.add(cfg['costs']['input_file'])
        configs.append((e, cfg))
    if len(sources) != 1:
        raise ValueError('Expected one shared source cost CSV; inspect multiple source paths.')
    original = safe(root, sources.pop())
    if sha(original) != SOURCE_HASH:
        raise ValueError('The source cost CSV differs from the audited upload. Nothing was replaced. Share that current CSV for review.')
    # Matched capped sweep for RQ2. D2 is already the 13.79% counterpart.
    for seed in ['C01','C03','C09','C11']:
        entry,cfg=next((e,c) for e,c in configs if e['scenario']==seed)
        newe=copy.deepcopy(entry);newe['scenario']='D_'+seed;newe['group']='cap_sweep'
        alt=copy.deepcopy(cfg);alt['co2']={'limit':8.8e6,'base':0.0}
        alt['nigeria_study'].update(scenario=newe['scenario'],group='cap_sweep',paired_reference=seed)
        configs.append((newe,alt))
    cache = cache_inventory(root,configs)
    # Check before writing: refuse to replace existing revision files.
    newdata, newcfg = safe(root, DATA_DIR), safe(root, NEW_DIR)
    if newdata.exists() or newcfg.exists():
        raise ValueError(f'{REVISION} already exists. Use audit/preflight/run; preparation never overwrites it.')
    for _, cfg in configs:
        if cfg['costs']['output_currency'] != 'USD' or int(cfg['costs']['price_year']) != 2024:
            raise ValueError('Expected the corrected USD2024 study, not the older EUR study.')
        if cfg['electricity']['max_hours']['battery'] != 6:
            raise ValueError('Battery duration changed; review the cost extrapolation before proceeding.')
    fields, rows = revised_rows(original)
    newdata.mkdir(parents=True)
    newcfg.mkdir(parents=True)
    (newdata/'costs_before.csv').write_bytes(original.read_bytes())
    with (newdata/'costs_revised.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    write_json(newdata/'assumptions.json', assumptions())
    write_json(newdata/'cache_inputs.json', cache)
    newentries = []
    def save_config(code, cfg, e, optional=False):
        p = newcfg/f'{code}.yaml'
        p.write_text(yaml.safe_dump(cfg, sort_keys=False))
        newentries.append({'scenario': code, 'group': cfg['nigeria_study']['group'],
            'optional_cost_check': optional, 'config': str(p.relative_to(root)),
            'config_sha256': sha(p), 'previous_config': e['config'], 'previous_config_sha256': e['config_sha256'],
            'run_name': cfg['run']['name'],
            'network': f"results/{cfg['run']['name']}/networks/elec_s_10_ec_lcopt_1h.nc"})
    for e, cfg in configs:
        code = e['scenario']
        cfg['run']['name'] = f'{REVISION}_{code}'
        for flag in ['download_osm_data','retrieve_cutout','build_cutout','retrieve_databundle',
                     'retrieve_databundle_sector','retrieve_cost_data','download_global_buildings','build_natura_raster']:
            cfg['enable'][flag]=False
        cfg['solving']['options']['load_shedding']=False
        cfg['costs']['input_file'] = str(DATA_DIR/'costs_revised.csv')
        price = float(cfg['nigeria_study']['gas_usd_per_mmbtu'])
        gas_cost = price*F_GAS/MMBTU_MWH
        cfg['costs'].setdefault('fuel', {})['gas'] = gas_cost
        cfg['costs']['marginal_cost'] = merged(cfg['costs'].get('marginal_cost', {}), {'solar': .01, 'onwind': .015})
        cfg['nigeria_study'].update(cost_data_revision=REVISION,
             gas_quote_period='June 2026', gas_real_2024_usd_per_mwh=gas_cost,
             cost_source_sha256=sha(newdata/'costs_revised.csv'),strict_demand=True,
             cached_physical_input_run=cache['source_run'])
        save_config(code, cfg, e)
        if code == 'B2':
            for extra in ['K_OCGT32', 'K_CCGT1450']:
                alt = copy.deepcopy(cfg)
                alt['run']['name'] = f'{REVISION}_{extra}'
                alt['nigeria_study'].update(scenario=extra, group='cost_sensitivity', paired_reference='B2')
                if extra == 'K_OCGT32':
                    alt['costs']['efficiency']['OCGT'] = .32
                    alt['nigeria_study']['cost_sensitivity'] = 'OCGT HHV efficiency 0.32 for existing and new; all other B2 inputs retained'
                else:
                    alt['costs'].setdefault('investment', {})['CCGT'] = 1450*F_LAZARD*1000
                    alt['costs'].setdefault('FOM', {})['CCGT'] = 100*25.5/1450
                    alt['nigeria_study']['cost_sensitivity'] = 'CCGT CAPEX 1450 USD July2026/kW; absolute FOM held at 25.5 USD July2026/kW/year'
                save_config(extra, alt, e, optional=True)
    write_json(newcfg/'manifest.json', newentries)
    write_json(newdata/'provenance.json', {'source_sha256':sha(original),
        'revised_sha256':sha(newdata/'costs_revised.csv'), 'tool_sha256':sha(__file__),
        'previous_manifest_sha256':sha(old_manifest), 'core_scenarios': len(configs), 'optional_cost_checks': 2,
        'excluded': ['B3', 'D3'], 'status': 'prepared; optimisation has not run'})
    print(f'PREPARED {len(configs)} core scenarios (25 retained + 4 capped counterparts), plus 2 cost checks. Existing files and results were preserved.')


def load_functions(root, isolated=False):
    if not isolated:
        sys.path.insert(0, str(root/'scripts'))
        from process_cost_data import load_costs
        return load_costs
    # Dependency-light verification of the ACTUAL three cost functions, unmodified
    # except for resolving their single helper import from the same source files.
    import pandas as pd
    ns = {'pd': pd, 'logger': logging.getLogger('cost-review'), 're': re}
    p = root/'scripts/nigeria_consistency.py'
    t = ast.parse(p.read_text())
    f = [n for n in t.body if isinstance(n, ast.FunctionDef) and n.name == 'convert_explicit_currency']
    exec(compile(ast.Module(body=f, type_ignores=[]), str(p), 'exec'), ns)
    p = root/'scripts/process_cost_data.py'; t = ast.parse(p.read_text())
    names = {'annuity', 'apply_discountrate_groups', 'load_costs'}
    nodes = [n for n in t.body if isinstance(n, ast.FunctionDef) and n.name in names]
    class ResolveHelper(ast.NodeTransformer):
        def visit_ImportFrom(self, node):
            return ast.copy_location(ast.Pass(), node) if node.module == 'nigeria_consistency' else node
    t = ResolveHelper().visit(ast.Module(body=nodes, type_ignores=[]))
    ast.fix_missing_locations(t)
    exec(compile(t, str(p), 'exec'), ns)
    return ns['load_costs']


def entries(root, codes=None, include_optional=False):
    rows = json.loads(safe(root, NEW_DIR/'manifest.json').read_text())
    if codes:
        unknown = set(codes)-{e['scenario'] for e in rows}
        if unknown:
            raise ValueError(f'Unknown/excluded scenarios: {sorted(unknown)}')
        rows = [e for e in rows if e['scenario'] in codes]
    elif not include_optional:
        rows = [e for e in rows if not e.get('optional_cost_check')]
    for e in rows:
        if sha(safe(root, e['config'])) != e['config_sha256']:
            raise ValueError(f"Configuration changed: {e['config']}. Do not mix edited inputs with saved results.")
        if sha(safe(root, e['previous_config'])) != e['previous_config_sha256']:
            raise ValueError(f"Original configuration changed after preparation: {e['previous_config']}")
    prov = json.loads(safe(root, DATA_DIR/'provenance.json').read_text())
    if sha(safe(root, DATA_DIR/'costs_revised.csv')) != prov['revised_sha256']:
        raise ValueError('Revised source changed after preparation.')
    return rows


def audit(root, codes=None, isolated=False, include_optional=False):
    import yaml
    import pandas as pd
    loader = load_functions(root, isolated)
    base = yaml.safe_load((root/'config.default.yaml').read_text())
    comparisons, checks, parameters = [], [], []
    def eq(value, expected, label):
        if not math.isclose(float(value), float(expected), rel_tol=1e-10, abs_tol=1e-7):
            raise ValueError(f'{label}: {value} != {expected}')
    for e in entries(root, codes, include_optional):
        cfg = merged(base, yaml.safe_load(safe(root, e['config']).read_text()))
        old = merged(base, yaml.safe_load(safe(root, e['previous_config']).read_text()))
        c = loader(root/cfg['costs']['input_file'], cfg['costs'], cfg['electricity']['max_hours'], 1.)
        before = loader(root/DATA_DIR/'costs_before.csv', old['costs'], old['electricity']['max_hours'], 1.)
        for t in ['solar', 'onwind', 'CCGT', 'OCGT', 'hydro', 'battery storage', 'battery inverter', 'HVAC overhead']:
            if not math.isfinite(float(c.at[t, 'capital_cost'])) or c.at[t, 'capital_cost'] <= 0:
                raise ValueError(f'Invalid annual cost: {t}')
            life, r = float(c.at[t,'lifetime']), float(c.at[t,'discount rate'])
            a = 1/life if r == 0 else r/(-math.expm1(-life*math.log1p(r)))
            eq(c.at[t,'capital_cost'], c.at[t,'investment']*(a+c.at[t,'FOM']/100), f'{t} annuity/units')
            comparisons.append({'scenario':e['scenario'], 'technology':t,
                'before_annual_cost':before.at[t,'capital_cost'], 'revised_annual_cost':c.at[t,'capital_cost'],
                'annual_cost_change_percent':100*(c.at[t,'capital_cost']/before.at[t,'capital_cost']-1),
                'discount_rate':r, 'lifetime_years':life})
        for t in ['CCGT','OCGT']:
            eq(c.at[t,'marginal_cost'], c.at['gas','fuel']/c.at[t,'efficiency']+c.at[t,'VOM'], f'{t} fuel conversion')
            eq(c.at[t,'efficiency'], cfg['costs']['efficiency'][t], f'{t} scenario efficiency')
        eq(c.at['battery','capital_cost'], c.at['battery inverter','capital_cost']+6*c.at['battery storage','capital_cost'], 'battery annualisation')
        eq(c.at['battery inverter','investment']+4*c.at['battery storage','investment'], 1000*BESS_2025*F_2025*4, 'four-hour reconstruction')
        eq(c.at['gas','fuel'], cfg['nigeria_study']['gas_usd_per_mmbtu']*F_GAS/MMBTU_MWH, 'gas price period')
        eq(c.at['solar','capital_cost'], c.at['solar-utility','capital_cost'], 'utility solar override')
        eq(c.at['solar','marginal_cost'], .01, 'solar dispatch tie breaker')
        eq(c.at['HVAC overhead','capital_cost'], before.at['HVAC overhead','capital_cost'], 'unchanged transmission')
        for t in ['solar','CCGT','OCGT']:
            eq(c.at[t,'discount rate'], before.at[t,'discount rate'], f'{t} unchanged WACC')
        checks.append({'scenario': e['scenario'], 'cost_checks': 'PASS',
            'method': 'isolated actual functions' if isolated else 'full project import',
            'gas_usd2024_mwh_thermal':float(c.at['gas','fuel']),
            'ccgt_marginal_usd2024_mwh_e':float(c.at['CCGT','marginal_cost']),
            'ocgt_marginal_usd2024_mwh_e':float(c.at['OCGT','marginal_cost'])})
        if cfg['solving']['options'].get('load_shedding') is not False or not cfg['nigeria_study'].get('strict_demand'):
            raise ValueError('Final scenarios must disable load shedding.')
        if e['scenario']=='B2':
            c.reset_index().to_csv(root/DATA_DIR/'processed_costs_B2.csv', index=False)
    out = root/DATA_DIR
    pd.DataFrame(comparisons).to_csv(out/'annual_cost_comparison.csv', index=False)
    pd.DataFrame(checks).to_csv(out/'verification_checks.csv', index=False)
    if not isolated:
        import importlib.metadata
        versions = {}
        for name in ['pypsa','atlite','pandas','numpy','linopy','snakemake']:
            try: versions[name] = importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError: versions[name] = 'not found'
        record = {'versions': versions, 'solar_reference':
            'IRENA solar CAPEX is per kW_DC; confirm the installed profile normalisation uses panel-rated capacity before final capacity reporting.'}
        try:
            import inspect
            import numpy as np
            import xarray as xr
            import atlite.resource
            import atlite.pv.solar_panel_model as panel_model
            panel=atlite.resource.get_solarpanelconfig('CSi')
            record['CSi_panel'] = panel
            record['pv_model_file_sha256'] = sha(panel_model.__file__)
            (out/'solar_panel_model_runtime.txt').write_text(inspect.getsource(panel_model))
            # At the panel model's reference module temperature/irradiance,
            # the no-inverter-loss output should be 1 per panel-rated unit.
            if panel.get('model')=='huld':
                irr=float(panel['r_irradiance'])
                ambient=(float(panel['r_tmod'])-float(panel['c_temp_irrad'])*irr)/float(panel['c_temp_amb'])
                ds=xr.Dataset({'temperature':('time',[ambient])},coords={'time':[0]})
                irradiation=xr.DataArray([irr],dims=['time'],coords={'time':[0]})
                no_loss=dict(panel,inverter_efficiency=1.0)
                a=float(np.asarray(panel_model.SolarPanelModel(ds,irradiation,no_loss)).ravel()[0])
                b=float(np.asarray(panel_model.SolarPanelModel(ds,irradiation,panel)).ravel()[0])
                record['pv_reference_probe']={'without_inverter_loss':a,'with_configured_inverter':b,
                    'expected_inverter_efficiency':float(panel['inverter_efficiency']),
                    'panel_normalisation_check_passed':bool(np.isclose(a,1.,atol=1e-6) and np.isclose(b,float(panel['inverter_efficiency']),atol=1e-6)),
                    'scope':'Tests installed panel model normalisation; does not verify AC/DC basis of the inherited existing-fleet statistics'}
        except (ImportError, AttributeError, TypeError, OSError, KeyError, ValueError) as exc:
            record['pv_evidence_note'] = str(exc)
        cache=json.loads((out/'cache_inputs.json').read_text())
        import pypsa
        base_network=pypsa.Network(root/'networks'/cache['source_run']/'base.nc')
        for col in ['objective','generators','stores']:
            eq(base_network.snapshot_weightings[col].sum(),8760.,f'cached base {col} annual hours')
        record['cached_base_annual_weightings_checked']=True
        (out/'runtime_evidence.json').write_text(json.dumps(record, indent=2, default=str)+'\n')
    print(f'COST_CHECKS_PASSED {len(checks)} scenarios; mode={checks[0]["method"]}. No optimisation run.')


def verify_final_network(n,cfg,metrics,root):
    """Check model assumptions and accounting before exporting a final result."""
    import numpy as np
    import pandas as pd
    if n.generators.carrier.isin(['load','load shedding']).any():
        raise ValueError('Unexpected unmet-demand generator in strict-demand final network.')
    if abs(metrics['unserved_twh'])>1e-10:
        raise ValueError('Strict-demand network reports unserved energy.')
    if abs(metrics['power_balance_residual_mw'])>.01:
        raise ValueError('Power balance residual exceeds 0.01 MW; inspect solver tolerances.')
    for col in ['objective','generators','stores']:
        if not np.isclose(n.snapshot_weightings[col].sum(),8760.,atol=1e-5,rtol=0):
            raise ValueError(f'{col}: annual weights are not 8760 hours.')
    if not np.isclose(metrics['demand_twh'],78.,atol=1e-6,rtol=0):
        raise ValueError('Final connected-network demand differs from 78 TWh.')
    for tech in ['CCGT','OCGT']:
        ids=n.generators.index[n.generators.carrier.eq(tech)]
        for name in ids:
            new=bool(n.generators.at[name,'p_nom_extendable'])
            limit=cfg['nigeria_study']['new_gas_availability'] if new else cfg['nigeria_study']['existing_gas_derating'][tech]
            if not np.isclose(n.generators.at[name,'p_max_pu'],limit):
                raise ValueError(f'Unexpected gas availability bound: {name}')
            if not np.isclose(n.generators.at[name,'efficiency'],cfg['costs']['efficiency'][tech]):
                raise ValueError(f'Unexpected gas efficiency: {name}')
    cap=cfg['co2'].get('limit')
    if cap is not None and metrics['emissions_mt']>cap/1e6+1e-4:
        raise ValueError('Emissions exceed the cap beyond the reporting tolerance of 100 tonnes.')
    loader=load_functions(root)
    import yaml
    base=yaml.safe_load((root/'config.default.yaml').read_text())
    cc=merged(base,cfg)
    c=loader(root/cc['costs']['input_file'],cc['costs'],cc['electricity']['max_hours'],1.)
    if len(n.lines):
        # Clustered line lengths already include the routing-length convention.
        # prepare_network refreshes their costs using those final lengths.
        expected=n.lines['length']*float(c.at['HVAC overhead','capital_cost'])
        if not np.allclose(n.lines.capital_cost,expected,rtol=1e-7,atol=1e-4):
            raise ValueError('Transmission annual costs do not match final line length times unit cost.')
    if sha(root/DATA_DIR/'costs_revised.csv')!=cfg['nigeria_study']['cost_source_sha256']:
        raise ValueError('Final network cost input no longer matches its recorded source hash.')


def run(root, codes, cores, dry_run, include_optional=False):
    import yaml
    rows = entries(root, codes,include_optional)
    audit(root, codes, isolated=False,include_optional=include_optional)
    stage_cache(root,rows)
    logdir = root/'logs'/REVISION; logdir.mkdir(parents=True, exist_ok=True)
    for e in rows:
        overlay=yaml.safe_load((root/e['config']).read_text())
        # Always preview before execution. Only the approved cost-dependent
        # rules can participate in either DAG, even if caches are missing.
        for preview in ([True] if dry_run else [True,False]):
            cmd=checked_command(e['config'],cores,preview,has_cap=bool(overlay['co2'].get('limit')))
            print('Preview:' if preview else 'Running:', ' '.join(cmd),flush=True)
            with (logdir/(e['scenario']+('_dryrun' if preview else '')+'.log')).open('w') as log:
                proc=subprocess.Popen(cmd,cwd=root,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
                for line in proc.stdout:
                    print(line,end='',flush=True);log.write(line)
                    m=re.search(r'^(?:local)?rule\s+([A-Za-z_][A-Za-z_0-9]*):',line.strip())
                    if m and m.group(1) not in ALLOWED_RULES:
                        proc.terminate();proc.wait()
                        raise ValueError(f'Unexpected upstream job {m.group(1)}; stopped before continuing.')
                if proc.wait():raise RuntimeError(f"Stopped at {e['scenario']}; see {logdir}")
        if not dry_run:
            import pypsa
            sys.path.insert(0, str(root/'analysis'))
            from nigeria_results import validate_metadata, extract_metrics
            n = pypsa.Network(root/e['network'])
            cfg = yaml.safe_load((root/e['config']).read_text())
            validate_metadata(n, cfg)
            m = extract_metrics(n)
            verify_final_network(n,cfg,m,root)
            write_json(logdir/(e['scenario']+'_checked.json'), {'scenario':e['scenario'],
                 'objective_usd':m['objective_usd'], 'unserved_share':m['unserved_share'],
                 'network_sha256':sha(root/e['network']), 'cost_source_sha256':sha(root/DATA_DIR/'costs_revised.csv')})
            print(f"SOLVED_AND_CHECKED {e['scenario']} unserved_share={m['unserved_share']:.9g}", flush=True)


def collect(root, partial, include_optional=False):
    import pandas as pd
    import pypsa
    import yaml
    sys.path.insert(0, str(root/'analysis'))
    from nigeria_results import validate_metadata, extract_metrics
    data, missing = [], []
    for e in entries(root, include_optional=include_optional):
        p = root/e['network']
        if not p.is_file():
            missing.append(e['scenario']); continue
        n = pypsa.Network(p)
        current=yaml.safe_load((root/e['config']).read_text())
        validate_metadata(n,current)
        m = extract_metrics(n)
        verify_final_network(n,current,m,root)
        m.update(network_sha256=sha(p), network_path=e['network'], cost_revision=REVISION,
                 cost_source_sha256=sha(root/DATA_DIR/'costs_revised.csv'),
                 paired_reference=current['nigeria_study'].get('paired_reference',''))
        data.append(m)
    if missing and not partial:
        raise ValueError(f'Missing scenarios: {missing}. Finish them or explicitly use --allow-partial.')
    if not data:
        raise ValueError('No revised networks found.')
    dest = root/'analysis/output'/REVISION; dest.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(data)
    cols = [c for c in df if c.startswith(('generation_','capacity_','new_')) and not c.endswith('utilisation')]
    df[cols] = df[cols].fillna(0.)
    df.to_csv(dest/'metrics.csv',index=False)
    indexed=df.set_index('scenario');pairs=[]
    for capped,uncapped in [('D1','B1'),('D2','B2'),('D_C01','C01'),('D_C03','C03'),('D_C09','C09'),('D_C11','C11')]:
        if capped not in indexed.index or uncapped not in indexed.index:continue
        a=indexed.loc[capped];b=indexed.loc[uncapped]
        pairs.append({'capped':capped,'unconstrained':uncapped,'renewable_real_wacc':b.renewable_wacc,
            'gas_real_wacc':b.gas_wacc,'unconstrained_planning_cost_usd':b.planning_supply_cost_usd,
            'capped_planning_cost_usd':a.planning_supply_cost_usd,
            'premium_usd':a.planning_supply_cost_usd-b.planning_supply_cost_usd,
            'premium_percent':100*(a.planning_supply_cost_usd/b.planning_supply_cost_usd-1)})
    pd.DataFrame(pairs).to_csv(dest/'matched_cap_premiums.csv',index=False)
    write_json(dest/'coverage.json', {'available':df.scenario.tolist(), 'missing':missing})
    print(f'SAVED {dest / "metrics.csv"}; {len(data)} scenarios, {len(missing)} missing')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--project',type=Path,default=Path.cwd())
    sub = p.add_subparsers(dest='action',required=True)
    sub.add_parser('prepare')
    a = sub.add_parser('audit'); a.add_argument('--isolated',action='store_true'); a.add_argument('--scenarios',nargs='+')
    a = sub.add_parser('preflight'); a.add_argument('--scenarios',nargs='+')
    a = sub.add_parser('run'); a.add_argument('--scenarios',nargs='+'); a.add_argument('--cores',type=int,default=4); a.add_argument('--dry-run',action='store_true');a.add_argument('--include-cost-checks',action='store_true')
    a = sub.add_parser('collect'); a.add_argument('--allow-partial',action='store_true'); a.add_argument('--include-cost-checks',action='store_true')
    args = p.parse_args(); root = args.project.resolve()
    if not (root/'Snakefile').is_file():
        p.error('Run from the pypsa-earth project folder, or supply --project PATH before the action.')
    if args.action=='prepare': prepare(root)
    elif args.action in {'audit','preflight'}: audit(root,args.scenarios,getattr(args,'isolated',False))
    elif args.action=='run': run(root,args.scenarios,args.cores,args.dry_run,args.include_cost_checks)
    elif args.action=='collect': collect(root,args.allow_partial,args.include_cost_checks)


if __name__=='__main__':
    try:
        main()
    except (ValueError, OSError, RuntimeError) as exc:
        print(f'STOPPED: {exc}',file=sys.stderr)
        raise SystemExit(1)
