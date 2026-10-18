"""Architecture inventory from manifests and Python imports; no dependency install."""
import ast
import json
from pathlib import PurePosixPath


def architecture(files):
    imports, routes, dependencies, entrypoints = [], [], [], []
    for path, source in sorted(files.items()):
        name=PurePosixPath(path).name
        if name in {'main.py','app.py','manage.py','server.js','index.js','main.go','Dockerfile','docker-compose.yml'}:
            entrypoints.append(path)
        if name.startswith('requirements') and name.endswith('.txt'):
            dependencies.extend({'manifest':path,'declaration':line.strip()} for line in source.splitlines() if line.strip() and not line.lstrip().startswith('#'))
        if name=='package.json':
            try:
                manifest=json.loads(source)
                for key in ['dependencies','devDependencies']:
                    deps=manifest.get(key,{})
                    if isinstance(deps,dict):
                        dependencies.extend({'manifest':path,'declaration':f'{k}: {v} ({key})'} for k,v in deps.items())
            except (ValueError,AttributeError): pass
        if not path.endswith('.py'): continue
        try: tree=ast.parse(source)
        except (SyntaxError,RecursionError): continue
        for node in ast.walk(tree):
            if isinstance(node,ast.Import):
                imports.extend({'file':path,'module':alias.name,'line':node.lineno} for alias in node.names)
            elif isinstance(node,ast.ImportFrom):
                imports.append({'file':path,'module':'.'*node.level+(node.module or ''),'line':node.lineno})
            elif isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator,ast.Call) and isinstance(decorator.func,ast.Attribute) and decorator.func.attr in {'get','post','put','patch','delete','route'} and decorator.args and isinstance(decorator.args[0],ast.Constant) and isinstance(decorator.args[0].value,str):
                        routes.append({'file':path,'line':node.lineno,'method':decorator.func.attr.upper(),'path':decorator.args[0].value,'handler':node.name})
    return {'entrypoints':entrypoints,'imports':imports,'routes':routes,'dependencies':dependencies,'note':'Detected statically. Imports are not a resolved dependency graph; versions are not checked for vulnerabilities.'}
