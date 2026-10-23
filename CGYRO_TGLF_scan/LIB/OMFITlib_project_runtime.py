"""One editable GACODE environment, synchronized to native module settings."""
from builtins import any, bool, dict, int, isinstance, list, str, tuple
from collections import OrderedDict
import copy
import re
from pathlib import PurePosixPath
from OMFITlib_cgyro_launch import command_template
from OMFITlib_gacode_installations import (INSTALL_DEFAULTS, initialize_installations,
    installation_issues, program_environment, sync_environment)
from OMFITlib_server_capabilities import matching_profile, resource_issues


TARGETS = OrderedDict([
    ('project', ()), ('scan', ('TGLF_scan',)),
    ('cgyro', ('CGYRO_scan',)), ('transfer', ('Transfer_tool',)),
    ('tglf', ('TGLF_scan', 'TGLF')), ('tgyro', ('TGLF_scan', 'TGYRO')),
    ('profiles', ('TGLF_scan', 'TGYRO', 'PROFILES_GEN')),
    ('trxpl', ('TGLF_scan', 'TGYRO', 'PROFILES_GEN', 'TRXPL')),
])
DEFAULTS = dict(serverPicker='', server='', tunnel='', workDir='', environment='',
    scheduler='slurm', queue='', wall_time='24:00:00', nodes=1, cores=16,
    cpus_per_task=1, array_parallel=40,
    cgyro_command='cgyro -e . -n {mpi} -nomp {threads}', tglf_command='tglf -e .',
    tgyro_command='tgyro -e . -n {n_radii}', prepare_command='tgyro -t . -n {n_radii}')
DEFAULTS.update(INSTALL_DEFAULTS)


def node_at(root, path):
    for key in path:
        if not isinstance(root, dict) or key not in root:
            return None
        root = root[key]
    return root


def text(mapping, key, default=''):
    try:
        return str(mapping.get(key, None) or default).strip()
    except Exception:
        return default


def initialize_runtime(root, factory=dict):
    settings = root['SETTINGS']
    if 'GACODE_RUNTIME' not in settings:
        values = copy.deepcopy(DEFAULTS)
        values.pop('gacode_installs')  # Allow literal legacy GACODE_ROOT migration.
        cg = node_at(root, TARGETS['cgyro']) or {}
        remote = cg.get('SETTINGS', {}).get('REMOTE_SETUP', {})
        picker = text(remote, 'serverPicker')
        cfg = remote.get(picker, {}) if picker else {}
        values['serverPicker'] = picker
        for key in ('server', 'tunnel', 'workDir'):
            values[key] = text(cfg, key) or text(remote, key)
        base = PurePosixPath(values['workDir'])
        if base.name.lower() in ('cgyro', 'tglf', 'tgyro', 'transfer', 'profiles'):
            values['workDir'] = str(base.parent)
        for key, legacy in [('scheduler', 'scheduler'), ('queue', 'queue'), ('wall_time', 'w'),
                            ('environment', 'environment'), ('cgyro_command', 'executable'),
                            ('nodes', 'nodes'), ('cores', 'ntasks_per_node'),
                            ('cpus_per_task', 'cpus_per_task'), ('array_parallel', 'array_parallel')]:
            if text(cfg, legacy):
                values[key] = cfg[legacy]
        if picker == 'localhost':
            values.update(dict(server='localhost', scheduler='local'))
        if not values['environment']:
            transfer = node_at(root, TARGETS['transfer']) or {}
            values['environment'] = text(transfer.get('SETTINGS', {}).get('SETUP', {}), 'executable')
        settings['GACODE_RUNTIME'] = factory()
        settings['GACODE_RUNTIME'].update(values)
    result = settings['GACODE_RUNTIME']
    initialize_installations(result, factory)
    for key, value in DEFAULTS.items():
        result.setdefault(key, copy.deepcopy(value))
    try:
        # Old projects copied a literal executable (-n 16) into this template.
        # Keep resource edits authoritative instead of freezing that old count.
        result['cgyro_command'] = command_template(result['cgyro_command'])
    except ValueError:
        pass  # Leave invalid text editable; validation supplies the explanation.
    sync_environment(result)
    return result


def runtime_values(config):
    return {key: copy.deepcopy(config.get(key, default)) for key, default in DEFAULTS.items()}


def server_registration_issues(config):
    """Validate only the connection fields needed to create a personal server."""
    issues = []
    picker, server = text(config, 'serverPicker'), text(config, 'server')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]*', picker) or picker.lower() in (
            'localhost', 'default', 'default_tunnel', 'idl', 'matlab') or picker.lower().endswith('_username'):
        issues.append('请填写独立的服务器配置名，例如 tyadmin09')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+@[A-Za-z0-9_.-]+(?::[0-9]+)?', server):
        issues.append('服务器地址请填写 用户名@主机 或 用户名@主机:端口，不加引号，不包含密码')
    elif ':' in server and not 1 <= int(server.rsplit(':', 1)[1]) <= 65535:
        issues.append('SSH 端口必须为 1 至 65535 的整数')
    if '\n' in text(config, 'tunnel') or '\r' in text(config, 'tunnel'):
        issues.append('连接隧道需要填写单行值')
    directory = text(config, 'workDir')
    if not directory:
        issues.append('请填写服务器上的工作根目录')
    else:
        path = PurePosixPath(directory)
        if not path.is_absolute() or '..' in path.parts or str(path) == '/':
            issues.append('工作根目录需要填写 Linux 绝对路径')
    return issues


def register_runtime_server(registry, config, factory):
    """Create a native NamelistName entry only after the Register button click."""
    issues = server_registration_issues(config)
    if issues:
        raise ValueError('；'.join(issues))
    picker = text(config, 'serverPicker')
    if picker in registry:
        raise ValueError('OMFIT 已有同名设置，不会覆盖；请在 OMFIT 个人服务器设置中修改：' + picker)
    entry = factory()
    entry.update(dict(server=text(config, 'server'), tunnel=text(config, 'tunnel')))
    if text(config, 'workDir'):
        entry['workDir'] = text(config, 'workDir').rstrip('/') + '/'
    registry[picker] = entry
    return picker


def validate_runtime(config):
    issues = []
    for key, label in [('serverPicker', 'OMFIT 服务器'), ('server', '服务器地址'), ('workDir', '工作根目录')]:
        if not text(config, key):
            issues.append(label + '未填写')
    path = PurePosixPath(text(config, 'workDir'))
    if not path.is_absolute() or '..' in path.parts or str(path) == '/':
        issues.append('工作根目录需要填写 Linux 绝对路径，例如 /work/home/用户名/OMFITtmp/gacode')
    scheduler = text(config, 'scheduler')
    if scheduler not in ('local', 'slurm', 'pbs'):
        issues.append('请选择本机、Slurm 或 PBS')
    elif (text(config, 'serverPicker') == 'localhost') != (scheduler == 'local'):
        issues.append('本机执行请配套选择 localhost 与本机调度；远程 CGYRO 扫描请选择 Slurm 或 PBS')
    if scheduler != 'local' and (str(path) == '/tmp' or str(path).startswith('/tmp/')):
        issues.append('Slurm / PBS 工作根目录必须位于计算节点可见的共享文件系统，不能使用 /tmp')
    for key, label in [('nodes', '节点数'), ('cores', '每节点 MPI 数'),
                       ('cpus_per_task', '每进程线程数'), ('array_parallel', '扫描并行点数')]:
        try:
            value = int(config[key])
            if value < 1 or str(value) != str(config[key]).strip():
                raise ValueError()
        except (TypeError, ValueError, KeyError):
            issues.append(label + '必须为正整数')
    if scheduler != 'local':
        for key, label in [('queue', '队列 / 分区'), ('wall_time', '时限')]:
            if not text(config, key) or '\n' in text(config, key) or '\r' in text(config, key):
                issues.append(label + '需要填写单行值')
    for key in ('cgyro_command', 'tglf_command', 'tgyro_command', 'prepare_command'):
        if not text(config, key):
            issues.append('运行命令不能为空：' + key)
    try:
        command_template(config.get('cgyro_command', ''))
    except ValueError as error:
        issues.append(str(error))
    return issues + installation_issues(config)


def applied_runtime(root):
    return root.get('PROJECT_STATE', {}).get('gacode_runtime', {}).get('applied', None)


def shared_issues(root):
    applied = applied_runtime(root)
    if applied is None:
        return []  # Existing projects retain their old setup until Apply.
    config = root['SETTINGS'].get('GACODE_RUNTIME', {})
    if not isinstance(config, dict) or not isinstance(applied, dict):
        return ['Saved runtime configuration is invalid; apply the configuration again']
    profile = matching_profile(config, root.get('PROJECT_STATE', {}).get('gacode_detection', {}))
    if runtime_values(config) != dict(applied):
        return ['统一环境配置已修改，请先在“环境配置”页应用']
    validation = validate_runtime(config) + resource_issues(config, profile)
    if validation:
        return validation
    for name, path in TARGETS.items():
        module = node_at(root, path)
        if module is None:
            continue
        settings = module['SETTINGS']
        remote = settings.get('REMOTE_SETUP', {})
        if not isinstance(remote, dict):
            return ['Invalid module remote settings: ' + name]
        try:
            endpoint, selected_fields, setup_fields = module_runtime_fields(
                applied, name, settings.get('SETUP', {}), profile)
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            return ['Invalid module runtime configuration ({}): {}'.format(name, exc)]
        if name == 'tgyro':
            # runTGYRObase expands this template using the actual DIR ranks.
            # Accept only that positive-integer substitution, not arbitrary
            # command/environment edits or a forced CGYRO allocation count.
            template = endpoint['environment'] + '\n' + str(applied['tgyro_command'])
            pattern = re.escape(template).replace(re.escape('{n_radii}'), r'[1-9][0-9]*')
            if re.fullmatch(pattern, str(settings.get('SETUP', {}).get('executable', ''))) is None:
                return ['TGYRO command differs from the applied template']
            setup_fields.pop('executable')
        selected = remote.get(endpoint['serverPicker'], {})
        for actual, expected in ((remote, endpoint), (selected, selected_fields),
                                 (settings.get('SETUP', {}), setup_fields)):
            if not isinstance(actual, dict) or any(str(actual.get(key, None)).strip() != str(value).strip()
                   for key, value in expected.items()):
                return ['Module runtime differs from the applied configuration: ' + name]
        if name == 'cgyro' and selected.get('server_capabilities', {}) != (profile or {}):
            return ['Server capabilities changed; apply the runtime configuration again']
    return []


def shared_multi_settings(root, settings):
    config = applied_runtime(root)
    if config is None:
        return
    settings.update(dict(execution='module', environment=config['environment'],
                    tgyro_environment=program_environment(config, 'tgyro'),
                    tglf_environment=program_environment(config, 'tglf'),
                    tgyro_command=config['prepare_command'], tglf_command=config['tglf_command']))


def target_program(name):
    return {'transfer': 'tgyro', 'trxpl': 'profiles'}.get(name, name)


def module_runtime_fields(values, name, setup, profile=None):
    """One runtime contract for both writing settings and checking drift.

    ``cores`` is a persisted legacy key: it denotes MPI ranks per node, not
    hardware cores including OpenMP threads. Transfer/TGYRO retain their
    radius-count contracts instead of inheriting CGYRO's rank allocation.
    """
    mpi_ranks = int(values['nodes']) * int(values['cores'])
    environment = program_environment(values, target_program(name))
    endpoint = dict(serverPicker=str(values['serverPicker']).strip(),
                    server=str(values['server']).strip(), tunnel=str(values['tunnel']),
                    workDir=str(PurePosixPath(str(values['workDir'])) / name) + '/',
                    environment=environment, scheduler=values['scheduler'],
                    queue=values['queue'], w=values['wall_time'])
    selected = dict(endpoint)
    selected.update(dict(nodes=int(values['nodes']), ntasks_per_node=int(values['cores']),
                         ppn=int(values['cores']), cpus_per_task=int(values['cpus_per_task']),
                         array_parallel=int(values['array_parallel']), n=mpi_ranks,
                         batch=values['scheduler'] != 'local'))
    update = dict(num_nodes=int(values['nodes']), num_cores=int(values['cores']),
                  wall_time=values['wall_time'], pbs_queue=values['queue'])
    if name == 'cgyro':
        selected['executable'] = command_template(values['cgyro_command']).replace(
            '{mpi}', str(mpi_ranks)).replace('{threads}', str(values['cpus_per_task']))
        update['cpus_per_task'] = int(values['cpus_per_task'])
    elif name == 'transfer':
        points = int(setup.get('p_tgyro', 3))
        selected.update(dict(nodes=1, ntasks_per_node=points, ppn=points, n=points, cpus_per_task=1))
        update.update(dict(num_nodes=1, num_cores=points, executable=environment,
                           profiles_environment=program_environment(values, 'profiles'),
                           gacode_shared=True, scheduler=values['scheduler']))
    elif name == 'tglf':
        selected['executable'] = str(values['tglf_command'])
        update['executable'] = environment + '\n' + str(values['tglf_command'])
    elif name == 'tgyro':
        update['gacode_command'] = str(values['tgyro_command'])
        update['executable'] = environment + '\n' + str(values['tgyro_command']).replace('{n_radii}', str(mpi_ranks))
    elif name == 'profiles':
        update['executable'] = environment + '\nprofiles_gen'
    return endpoint, selected, update


def apply_runtime(root, factory=dict):
    """Prepare configuration-only changes, then commit them as one transaction."""
    config = initialize_runtime(root, factory)
    profile = matching_profile(config, root.get('PROJECT_STATE', {}).get('gacode_detection', {}))
    issues = validate_runtime(config) + resource_issues(config, profile)
    if issues:
        raise ValueError('; '.join(issues))
    values = runtime_values(config)
    operations, backups = [], factory()
    missing = object()
    for name, path in TARGETS.items():
        module = node_at(root, path)
        if module is None:
            continue
        settings = module['SETTINGS']
        current = settings.get('REMOTE_SETUP', {})
        setup = settings.get('SETUP', None)
        if setup is None:
            setup = factory()
            operations.append((settings, 'SETUP', setup))
        endpoint, selected_fields, setup_fields = module_runtime_fields(values, name, setup, profile)
        # Copy only configuration, never module inputs, cases or result objects.
        remote = copy.deepcopy(current)
        remote.update(endpoint)
        selected = remote.setdefault(endpoint['serverPicker'], factory())
        selected.update(selected_fields)
        if name == 'cgyro':
            if profile:
                selected['server_capabilities'] = copy.deepcopy(profile)
            else:
                selected.pop('server_capabilities', None)
        operations.append((settings, 'REMOTE_SETUP', remote))
        backups[name] = dict(REMOTE_SETUP=copy.deepcopy(current),
                            SETUP={key: copy.deepcopy(dict.get(setup, key, None)) for key in setup_fields})
        operations.extend((setup, key, value) for key, value in setup_fields.items())

    # Include applied-state and multi-profile synchronization in the transaction:
    # an Abort here must not leave modules changed but the applied snapshot old.
    project_state = root.get('PROJECT_STATE', None)
    if project_state is None:
        project_state = factory()
        operations.append((root, 'PROJECT_STATE', project_state))
    runtime_state = copy.deepcopy(project_state.get('gacode_runtime', factory()))
    runtime_state.update(dict(previous=backups, applied=copy.deepcopy(values)))
    operations.append((project_state, 'gacode_runtime', runtime_state))
    multi = root['SETTINGS'].get('TGLF_MULTI', None)
    if multi is not None:
        updated_multi = copy.deepcopy(multi)
        shared_multi_settings({'PROJECT_STATE': {'gacode_runtime': runtime_state}}, updated_multi)
        operations.extend((multi, key, value) for key, value in updated_multi.items())
    completed = []
    try:
        for parent, key, value in operations:
            old = dict.get(parent, key, missing)
            completed.append((parent, key, old))
            parent[key] = value
    except BaseException as original_error:
        rollback_errors = []
        for parent, key, old in reversed(completed):
            try:
                if old is missing:
                    parent.pop(key, None)
                else:
                    parent[key] = old
            except BaseException as rollback_error:
                rollback_errors.append(str(rollback_error))
        if rollback_errors:
            original_error.runtime_rollback_errors = rollback_errors
        raise
    return list(backups)
