"""Executable regression of the refactored modules with real Matplotlib and fake OMFIT boundaries."""
import ast
import copy
import importlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
import warnings
from contextlib import nullcontext

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.backend_bases import MouseEvent
import numpy as np

BASE = Path(__file__).resolve().parent
_PREVIEW_TMP = tempfile.TemporaryDirectory()
PREVIEWS = Path(_PREVIEW_TMP.name)
PROJECT = BASE.parent
MODULE = PROJECT/'CGYRO_TGLF_scan'
sys.path.insert(0, str(MODULE/'LIB'))
modules = {name: importlib.import_module('OMFITlib_compare_'+name) for name in
           ('state','widgets','cases','ui','core','series','flux','style','spectra','tglf','dispatch','status',
            'cgyro_selection','cgyro_data','cgyro_eigen','cgyro_render','cgyro_export','cgyro')}
state, core, series = (modules[k] for k in ('state','core','series'))


def fixture(mode='CGYRO_vs_TGLF'):
    ky = np.array([.1,.2,.4,.8])
    times = np.arange(20)
    def cg_curve(value, shift):
        return {'lin': {str(k): {'n_time': len(times), 'kyrhos': k,
                'freq': {'omega': [np.full(20, value*(k-.4)+shift)],
                         'gamma': [np.full(20, value*k-.25)]},
                'input.cgyro.gen': {'N_SPECIES':2,'DENS_1':1.,'MASS_1':1.,'Z_1':1.}}
                for k in ky}}
    def tg_curve(value, shift):
        return {'eigenvalue_spectrum': {'ky': ky.copy(), 'freq(1)': value*(ky-.4)+shift,
                                       'gamma(1)': value*ky-.2},
                'fluxes': {'Gam/Gam_GB': np.array([value,2*value]), 'Q/Q_GB':np.array([2*value,3*value])}}
    cg = {'runid':'run', 'nr_selected':['nr=2'], 'selected_paras':{'A':[1.,2.]}}
    tg = {'spectra_mode':'1D', 'rho_selected':[.3], 'rho_pair_flags': {'nr=2':{'0.3':True}},
          'selected_paras': {'A':[1.]}}
    physics = {'compare_mode':mode, 'CGYRO_vs_TGLF':{'CGYRO':copy.deepcopy(cg),'TGLF':copy.deepcopy(tg)},
               'TGLF_vs_CGYRO':{'CGYRO':dict(copy.deepcopy(cg),rho_pair_cfg={'0.3':{'nr_selected':['nr=2','nr=10']}}),
                               'TGLF':copy.deepcopy(tg)},
               'TGLF_vs_TGLF':{'TGLF':copy.deepcopy(tg)},
               'CGYRO_vs_CGYRO':{'runid':'run','nr_CGYRO':['nr=2'], 'selected_paras':{'A':[1.,2.]},
                                 'ave_window':1.,'divide_by_ky':False,'error_filter':False}}
    root = {'SETTINGS':{'PHYSICS':physics},
            'CGYRO_scan':{'RUN_DB': {'run': {'nr=10': {'A': {v:cg_curve(v,.2) for v in (1.,2.)}},
                                                'nr=2': {'A': {v:cg_curve(v,.1) for v in (1.,2.)}}}}},
            'TGLF_scan': {
                'scanResults_spectra': {rho: {'A':{v:tg_curve(v,rho) for v in (1.,2.)}} for rho in (.3,.5)},
                'scanResults2D_spectra': {.3: {'A+B': {1.: {2.:tg_curve(1.,.3)},3.:{4.:tg_curve(3.,.3)}}}},
                'scanResults': {.3:{'A':{v:tg_curve(v,.3) for v in (1.,2.)}}},
                'scanResults2D': {.3:{'A+B':{1.:{2.:tg_curve(1.,.3)},3.:{4.:tg_curve(3.,.3)}}}},
            }, 'PLOTS': {}}
    state.initialize_settings(root)
    return root


class FakeUI:
    """Honor OMFIT widget default/binding behavior and record the produced layout."""
    def __init__(self, root):
        self.root, self.events = root, []
        self.tab = 'Header'

    def _ensure(self, path, default):
        if isinstance(path, list):
            for p,v in zip(path,default): self._ensure(p,v)
            return
        node = ast.parse(path,mode='eval').body
        keys = []
        while isinstance(node,ast.Subscript):
            keys.insert(0,ast.literal_eval(node.slice))
            node = node.value
        assert isinstance(node,ast.Name) and node.id == 'root', path
        target=self.root
        for key in keys[:-1]:
            target=target[key]  # Missing intermediate paths fail just like bound OMFIT widgets.
        target.setdefault(keys[-1],copy.deepcopy(default))

    def same_row(self):
        return nullcontext()

    def __getattr__(self, name):
        def call(*args, **kwargs):
            if name=='Tab': self.tab=args[0]
            if name in ('Entry','CheckBox','ComboBox'):
                self._ensure(args[0],kwargs.get('default'))
            self.events.append((self.tab,name,args,kwargs))
        return call


class Notebook:
    figures=[]
    def __init__(self,*args,**kwargs):
        self.name=args[-1] if args else ''
    def subplots(self,*args,**kwargs):
        label=kwargs.pop('label','')
        fig,ax=plt.subplots(*args,**kwargs)
        fig.set_label(label)
        self.figures.append(fig)
        return fig,ax


class RefactorTest(unittest.TestCase):
    def setUp(self):
        Notebook.figures=[]
        for module in modules.values(): module.FigureNotebook=Notebook
        self.root=fixture()

    def tearDown(self):
        plt.close('all')

    def render(self, root=None):
        root = root or self.root
        ui=FakeUI(root)
        app=modules['ui'].ComparisonUI(root,ui)
        app.render()
        return app,ui

    def test_import_graph_and_python39_syntax(self):
        for path in (MODULE/'LIB').glob('OMFITlib_compare_*.py'):
            source=path.read_text(encoding='utf-8')
            ast.parse(source,feature_version=(3,9))
            compile(source,str(path),'exec')
            self.assertNotIn('from numpy import *',source)

    def test_four_modes_have_same_ordered_tabs(self):
        for mode in state.MODES:
            app,ui=self.render(fixture(mode))
            tabs=[args[0] for _,name,args,_ in ui.events if name=='Tab']
            self.assertEqual(tabs,['1 案例选择','2 绘图设置','3 图形样式','4 导出与检查',''])
            self.assertTrue(any(tab=='' and name=='Button' and args[0]=='绘制所选数据'
                                for tab,name,args,_ in ui.events))
            self.assertFalse(state.selection_check(app.root)['errors'])

    def test_empty_project_panel_is_actionable(self):
        root={'SETTINGS':{'PHYSICS':{}}}
        for mode in state.MODES:
            root['SETTINGS']['PHYSICS']['compare_mode']=mode
            self.render(root)
            self.assertTrue(state.selection_check(root)['errors'])

    def test_selection_identity_survives_insert_reorder_delete(self):
        record={'nr_flag':{'0':True,'1':False}}
        state.sync_flags(record,'nr_flag',['nr=2','nr=10'])
        flags=state.sync_flags(record,'nr_flag',['nr=1','nr=10','nr=2'])
        self.assertEqual(state.selected_items(flags,['nr=1','nr=10','nr=2']),['nr=2'])
        self.assertFalse(any(state.sync_flags(record,'nr_flag',['nr=1','nr=10']).values()))

    def test_legacy_selected_keys_migrate_before_new_sort(self):
        record={'nr_flag':{'0':True}, 'nr_CGYRO':['nr=10']}
        flags=state.sync_flags(record,'nr_flag',['nr=2','nr=10'],'nr_CGYRO')
        self.assertEqual(state.selected_items(flags,['nr=2','nr=10']),['nr=10'])

    def test_source_switch_retains_independent_selections(self):
        record={'selected_paras':{'A':[0.,1.]}}
        state.activate_source(record,'1D')
        state.activate_source(record,'2D')
        self.assertNotIn('selected_paras',record)
        record['selected_paras_2d']={'A+B':{'para1_values':[2.],'para2_values':[3.]}}
        state.activate_source(record,'1D')
        self.assertEqual(record['selected_paras'],{'A':[0.,1.]})
        state.activate_source(record,'2D')
        self.assertIn('A+B',record['selected_paras_2d'])

    def test_zero_selection_and_partial_2d_validation(self):
        self.assertTrue(state.has_values(0.))
        self.assertFalse(state.has_values({'para1_values':[1.], 'para2_values':[]}))

    def test_quoted_keys_safe_gui_path(self):
        root={'SETTINGS':{'PHYSICS':{}}}
        key="a'\"\\]run"
        path=state.dict_path("root['SETTINGS']['PHYSICS']",key)
        FakeUI(root)._ensure(path,False)
        self.assertIn(key,root['SETTINGS']['PHYSICS'])

    def test_gui_never_mutates_result_tree(self):
        before=copy.deepcopy(self.root['CGYRO_scan'])
        order=list(self.root['CGYRO_scan']['RUN_DB']['run'])
        self.render()
        self.assertEqual(list(self.root['CGYRO_scan']['RUN_DB']['run']),order)
        np.testing.assert_equal(self.root['CGYRO_scan'],before)

    def test_invalid_average_and_transform_stop_before_plot(self):
        settings=self.root['SETTINGS']['PHYSICS']['CGYRO_vs_TGLF']['plot']
        for invalid in (0,-1,1.1,float('nan'),'bad'):
            settings['ave_window']=invalid
            self.assertTrue(state.selection_check(self.root)['errors'])
        settings['ave_window']=.02
        settings.update(divide_by_ky=True,divide_by_ky2=True)
        with self.assertRaises(ValueError): modules['dispatch'].run_plot(self.root)
        self.assertFalse(Notebook.figures)

    def test_ragged_2d_defaults_include_all_branches(self):
        root=fixture('TGLF_vs_TGLF')
        tg=root['SETTINGS']['PHYSICS']['TGLF_vs_TGLF']['TGLF']
        tg.update(spectra_mode='2D',selected_paras_2d={'A+B':{'para1_values':[1.,3.],'para2_values':[2.,4.]}})
        app,ui=self.render(root)
        tg['selected_paras_2d']={}
        self.render(root)
        np.testing.assert_equal(tg['selected_paras_2d']['A+B']['para2_values'],[2.,4.])

    def test_explicit_empty_2d_axis_is_not_all_values(self):
        self.assertEqual(core.get_2d_scan_values({1.:{2.:{}}},{'para1_values':[], 'para2_values':[2.]}),([], [2.]))

    def test_numeric_key_resolution_is_unambiguous(self):
        self.assertEqual(core.resolve_key({'1.00000':{}},1.),'1.00000')
        self.assertEqual(core.resolve_key({'1.0':{},'1.00':{}},1.), '1.0')
        with self.assertRaises(ValueError): core.resolve_key({'1.00':{},'1.000':{}},1.)

    def test_cgyro_raw_spectra_preserve_negative_gamma(self):
        ctx=core.build_context(self.root)
        result=series.collect_cgyro_series(self.root,ctx,'run','nr=2','A',1.)
        np.testing.assert_allclose(result[2],[-.15,-.05,.15,.55])
        np.testing.assert_allclose(result[3:],np.zeros((2,4)),atol=1e-14)

    def test_invalid_cgyro_samples_are_reported(self):
        node=self.root['CGYRO_scan']['RUN_DB']['run']['nr=2']['A'][1.]['lin']['0.1']
        node['n_time']=25
        ctx=core.build_context(self.root)
        data=series.collect_cgyro_series(self.root,ctx,'run','nr=2','A',1.)
        self.assertEqual(len(data[0]),3)
        self.assertIn('n_time',ctx['_diagnostics'][0])

    def test_tail_stats_zero_and_negative_means(self):
        out=core._tail_frequency_stats([-1.,1.],[-1.,-3.])
        self.assertTrue(np.isinf(out[0][2]))
        self.assertEqual(out[1],(-2.,1.,.5))
        self.assertEqual(core._tail_frequency_stats([0.,0.],[0.,0.]),[(0.,0.,0.),(0.,0.,0.)])

    def test_tglf_labels_are_unique_across_radii_parameters(self):
        curves=series.collect_tglf_curves([.3,.5],{'A':[1.]},self.root,core.build_context(self.root))
        self.assertEqual(len(set(c['label'] for c in curves)),2)
        self.assertTrue(all('rho=' in c['label'] and 'A=' in c['label'] for c in curves))
        self.assertTrue(all(not c['show_error'] for c in curves))

    def test_mismatched_spectrum_lengths_are_not_truncated(self):
        node=self.root['TGLF_scan']['scanResults_spectra'][.3]['A'][1.]['eigenvalue_spectrum']
        node['gamma(1)']=np.array([1.])
        ctx=core.build_context(self.root)
        self.assertEqual(len(series.collect_tglf_series(self.root,ctx,.3,'A',1.)[0]),0)
        self.assertIn('different lengths',ctx['_diagnostics'][0])

    def test_two_dimensional_only_and_optional_second_mode(self):
        ctx=core.build_context(self.root)
        ctx['tglf_state']={'spectra_mode':'2D'}
        curves=series.collect_tglf_curves(.3,{'A+B':{'para1_values':[1.],'para2_values':[2.]}},self.root,ctx)
        self.assertEqual(len(curves),1)
        self.assertEqual(len(series.collect_tglf_series(self.root,ctx,.3,'A+B',(1.,2.),mode_idx=2)[0]),0)

    def test_reverse_mode_reads_every_selected_radius(self):
        root=fixture('TGLF_vs_CGYRO')
        self.render(root)
        pages=list(modules['dispatch'].collect_comparison_pages(root,core.build_context(root)))
        self.assertEqual({c['nr'] for c in pages[0][1]},{'nr=2','nr=10'})

    def test_no_overlap_missing_and_single_point_errors(self):
        out=core.cgyro_tglf_error([.1],[1.],[2.],[.3],[1.],[2.])
        self.assertTrue(np.all(np.isnan(out)))
        out=core.cgyro_tglf_error([.1],[1.],[2.],[.1],[2.],[4.])
        np.testing.assert_allclose(out,[[1.],[1.]])

    def test_ambiguous_reference_rejected_before_figure(self):
        state_=self.root['SETTINGS']['PHYSICS']['CGYRO_vs_TGLF']
        state_['plot']['error_flag']='CGYRO-TGLF'
        state_['TGLF']['selected_paras']['A']=[1.,2.]
        with self.assertRaisesRegex(ValueError,'reference'): modules['dispatch'].run_plot(self.root)
        self.assertFalse(Notebook.figures)

    def test_ky_zero_is_masked_without_warning_or_infinity(self):
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            ky,om,ga=core.prepare_spectrum_for_plot(np.array([0.,.2]),np.ones(2),np.ones(2),True)
        self.assertTrue(np.isnan(om[0]) and np.isnan(ga[0]))
        self.assertEqual(om[1],5.)

    def test_real_matplotlib_overlay_and_style(self):
        s=self.root['SETTINGS']['PHYSICS']['CGYRO_vs_TGLF']
        s['plot'].update(error_flag='No_error',comparison_layout='Overlay',divide_by_ky=False)
        s['style'].update(figure_width=11.,figure_height=6.,legend_font_size=8.,line_width=2.2)
        modules['dispatch'].run_plot(self.root)
        self.assertEqual(len(Notebook.figures),1)
        fig=Notebook.figures[0]
        self.assertEqual(len(fig.axes),2)
        np.testing.assert_allclose(fig.get_size_inches(),[11.,6.])
        self.assertEqual(len(fig.axes[0].lines),3)
        self.assertEqual(fig.axes[0].lines[0].get_linewidth(),2.2)
        previews=PREVIEWS; previews.mkdir(exist_ok=True)
        fig.savefig(previews/'spectra_overlay.png',dpi=130)

    def test_real_matplotlib_difference_panels(self):
        s=self.root['SETTINGS']['PHYSICS']['CGYRO_vs_TGLF']
        s['plot'].update(error_flag='CGYRO-TGLF',divide_by_ky=False)
        modules['dispatch'].run_plot(self.root)
        fig=Notebook.figures[0]
        self.assertEqual(len(fig.axes),4)
        self.assertEqual(len(fig.axes[1].lines),2)
        self.assertEqual(fig.axes[0].lines[0].get_color(),fig.axes[1].lines[0].get_color())
        fig.savefig(PREVIEWS/'model_difference.png',dpi=130)

    def test_outside_legend_toggle_and_callback_replacement(self):
        fig,axes=plt.subplots(2,1,figsize=(7,5))
        ctx={'style':{'legend_location':'outside'},'fs2':8}
        for ax in axes:
            ax.plot([0,1],[0,1],label='case A')
            modules['style'].finalize_axis_legend(ax,ctx)
        fig.tight_layout()
        modules['style'].finalize_axis_legend(axes[0],ctx)
        fig.canvas.draw()
        box=axes[0].get_legend().get_texts()[0].get_window_extent(fig.canvas.get_renderer())
        click=MouseEvent('button_press_event',fig.canvas,(box.x0+box.x1)/2,(box.y0+box.y1)/2,button=1)
        self.assertIsNone(click.inaxes)
        fig.canvas.callbacks.process('button_press_event',click)
        self.assertTrue(all(not ax.lines[0].get_visible() for ax in axes))
        fig.canvas.callbacks.process('button_press_event',click)
        self.assertTrue(all(ax.lines[0].get_visible() for ax in axes))

    def test_tglf_only_1d_spectrum_and_flux_plot(self):
        for target in ('Spectra','Flux'):
            root=fixture('TGLF_vs_TGLF')
            root['SETTINGS']['PHYSICS']['TGLF_vs_TGLF']['plot'].update(tglf_vs_tglf_mode=target,show_flux_spectra=False)
            self.render(root)
            modules['dispatch'].run_plot(root)
        self.assertGreaterEqual(len(Notebook.figures),2)
        self.assertTrue(any('not available' in text.get_text() for fig in Notebook.figures for ax in fig.axes for text in ax.texts))

    def test_gamma_ratio_independent_of_display_scaling(self):
        curves=[dict(kind='CGYRO',para='A',value=v,ky=np.array([.1,1.]),omega=np.ones(2),gamma=np.array(g))
                for v,g in [(1,[1.,2.]),(2,[2.,3.])]]
        ctx=core.build_context(self.root)
        ctx.update(gamma_ref_value='1',gamma_ref_mode='all ky')
        for d,d2 in ((False,False),(True,False),(False,True)):
            ctx.update(divide_by_ky=d,divide_by_ky2=d2)
            np.testing.assert_allclose(modules['spectra']._compute_gamma_ratio_for_group(curves,ctx)[1],[1.,1.5])

    def test_export_preserves_signed_data_and_existing_exports(self):
        ctx=core.build_context(self.root)
        pages=list(modules['dispatch'].collect_comparison_pages(self.root,ctx))
        with tempfile.TemporaryDirectory() as tmp:
            ctx['mode_state']['linear_export_dir']=tmp
            p1=Path(modules['dispatch'].export_comparison(self.root,ctx,pages))
            original=(p1/'spectra.csv').read_bytes()
            p2=Path(modules['dispatch'].export_comparison(self.root,ctx,pages))
            self.assertNotEqual(p1,p2)
            self.assertEqual(original,(p1/'spectra.csv').read_bytes())
            self.assertIn('-0.15',original.decode('utf-8-sig'))
            self.assertTrue((p2/'metadata.json').exists())

    def test_buttons_use_omfit_cache_and_restore_action_flags(self):
        app,ui=self.render()
        class Node:
            def plot(self): raise RuntimeError('synthetic failure')
            def reload(self): raise AssertionError('Must not discard editor changes')
        self.root['PLOTS']['CGYRO_vs_TGLF']=Node()
        app._select_export_directory=lambda *args: str(BASE)
        with self.assertRaisesRegex(RuntimeError,'synthetic'): app._export()
        self.assertFalse(app.state['comparison_export_now'])

    def test_compatibility_shortcut(self):
        root=fixture()
        root['GUIS']={'CGYRO_vs_TGLF':'unified'}
        ui=FakeUI(root)
        source=(MODULE/'GUIS/CGYRO_vs_CGYRO.py').read_text(encoding='utf-8')
        exec(compile(source,'shortcut','exec'),{'root':root,'OMFITx':ui})
        self.assertEqual(root['SETTINGS']['PHYSICS']['compare_mode'],'CGYRO_vs_CGYRO')
        self.assertTrue(any(name=='CompoundGUI' for _,name,_,_ in ui.events))

    def test_cgyro_self_comparison_without_adjusttext(self):
        root=fixture('CGYRO_vs_CGYRO')
        self.render(root)
        modules['cgyro'].run_plot(root)
        self.assertEqual(len(Notebook.figures),1)
        self.assertEqual(len(Notebook.figures[0].axes),4)

    def test_tglf_2d_spectra_and_flux_use_selected_varying_axis(self):
        root=fixture('TGLF_vs_TGLF')
        tg=root['SETTINGS']['PHYSICS']['TGLF_vs_TGLF']['TGLF']
        tg.update(spectra_mode='2D', selected_paras_2d={'A+B':{'para1_values':[1.,3.],'para2_values':[2.,4.]}})
        settings=root['SETTINGS']['PHYSICS']['TGLF_vs_TGLF']['plot']
        for target in ('Spectra','Flux'):
            settings.update(tglf_vs_tglf_mode=target, tglf2d_x_axis='para1', show_flux_spectra=False)
            self.render(root)
            # Switching source intentionally clears selections for a previously unseen tree.
            tg.update(rho_selected=[.3], selected_paras_2d={'A+B':{'para1_values':[1.,3.],'para2_values':[2.,4.]}})
            modules['dispatch'].run_plot(root)
        self.assertGreaterEqual(len(Notebook.figures),2)
        spectral_labels=[line.get_label() for ax in Notebook.figures[0].axes for line in ax.lines]
        self.assertTrue(any('B=2' in label for label in spectral_labels),spectral_labels)
        flux_figure=Notebook.figures[-1]
        self.assertEqual(flux_figure.axes[0].get_xlabel(),'A')

    def test_tglf_3d_ragged_spectra_render_without_second_mode(self):
        root=fixture('TGLF_vs_TGLF')
        record=root['SETTINGS']['PHYSICS']['TGLF_vs_TGLF']
        record['TGLF'].update(spectra_mode='2D',selected_paras_2d={'A+B':{'para1_values':[1.,3.],'para2_values':[2.,4.]}})
        record['plot'].update(tglf2d_plot_mode='3D',tglf2d_x_axis='para2',show_flux_spectra=False)
        self.render(root)
        modules['dispatch'].run_plot(root)
        self.assertTrue(Notebook.figures)
        for fig in Notebook.figures: fig.canvas.draw()

    def test_runtime_globals_resolve_without_numpy_star(self):
        import builtins
        import symtable
        unresolved={}
        for name,module in modules.items():
            source=Path(module.__file__).read_text(encoding='utf-8')
            def visit(table):
                for symbol in table.get_symbols():
                    key=symbol.get_name()
                    if (symbol.is_global() and symbol.is_referenced() and key not in module.__dict__
                            and not hasattr(builtins,key) and key not in ('FigureNotebook','__class__')):
                        unresolved.setdefault(name,set()).add(key)
                for child in table.get_children(): visit(child)
            visit(symtable.symtable(source,module.__file__,'exec'))
        self.assertEqual(unresolved,{})

    def test_omfit_pylab_namespace_cannot_shadow_builtin_reductions(self):
        import builtins
        env={'min':np.min,'max':np.max,'all':np.all,'any':np.any,'sum':np.sum}
        source=Path(core.__file__).read_text(encoding='utf-8')
        exec(compile(source,core.__file__,'exec'),env)
        self.assertIs(env['max'],builtins.max)
        self.assertIs(env['all'],builtins.all)
        self.assertEqual(env['_tail_frequency_stats']([-3.,-1.],[-3.,-1.])[0],(-2.,1.,.5))

    def test_grid_toggle_is_effective(self):
        fig,ax=plt.subplots()
        ax.plot([0,1],[0,1])
        with warnings.catch_warnings():
            warnings.simplefilter('error')
            modules['style'].apply_figure_layout(fig,{'style':{'show_grid':False}})
        self.assertFalse(any(line.get_visible() for line in ax.get_xgridlines()+ax.get_ygridlines()))

    def test_all_omfit_file_registrations_resolve_in_result_free_project(self):
        sys.path.insert(0, str(PROJECT / 'OMFITtemplates/LIB'))
        from OMFITlib_template_archive import parse_tree
        for row in parse_tree((PROJECT / 'OMFITsave.txt').read_bytes()):
            if row.ref:
                self.assertTrue((PROJECT / row.ref).exists(), row.ref)
        self.assertFalse((PROJECT / '__COMMANDBOX__').exists())
        self.assertFalse(list(PROJECT.rglob('*.npy')))

    def test_comparison_button_opens_sibling_module_with_its_own_library_scope(self):
        from unittest.mock import Mock
        root = fixture()
        ui = FakeUI(root)
        manager_gui = Mock()
        omfit = {'OMFITtemplates': {'GUIS': {'main': manager_gui}}}
        entry = (MODULE / 'GUIS/CGYRO_vs_TGLF.py').read_text(encoding='utf-8')
        exec(compile(entry, 'CGYRO_vs_TGLF.py', 'exec'), {'root': root, 'OMFITx': ui, 'OMFIT': omfit})
        buttons = [args for _, kind, args, _ in ui.events if kind == 'Button' and args[0] == '模板 / GitHub']
        self.assertEqual(len(buttons), 1)
        buttons[0][1]()
        manager_gui.run.assert_called_once_with()

    def test_default_gui_handles_a_project_with_no_calculations(self):
        from unittest.mock import Mock
        settings = json.loads((MODULE / 'SettingsNamelist.txt').read_bytes())
        root = {'SETTINGS': settings, 'CGYRO_scan': {'RUN_DB': {}}, 'TGLF_scan': {}}
        ui = FakeUI(root)
        modules['ui'].ComparisonUI(root, ui).render(open_templates=Mock())
        report = state.selection_check(root)
        self.assertTrue(report['errors'])
        self.assertEqual(root['CGYRO_scan']['RUN_DB'], {})


if __name__=='__main__':
    (PREVIEWS).mkdir(exist_ok=True)
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(RefactorTest)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    report={'tests':result.testsRun,'passed':result.wasSuccessful(),
            'failures':[(str(case),text) for case,text in result.failures+result.errors]}
    print(json.dumps(report))
    raise SystemExit(not result.wasSuccessful())
