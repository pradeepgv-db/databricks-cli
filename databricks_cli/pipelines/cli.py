# Databricks CLI
# Copyright 2017 Databricks, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"), except
# that the use of services to which certain application programming
# interfaces (each, an "API") connect requires that the user first obtain
# a license for the use of the APIs from Databricks, Inc. ("Databricks"),
# by creating an account at www.databricks.com and agreeing to either (a)
# the Community Edition Terms of Service, (b) the Databricks Terms of
# Service, or (c) another written agreement between Licensee and Databricks
# for the use of the APIs.
#
# You may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import json
import string
import requests

try:
    from urlparse import urlparse, urljoin
except ImportError:
    from urllib.parse import urlparse, urljoin

import click

from databricks_cli.click_types import PipelineSpecClickType, \
    PipelineSettingClickType, PipelineIdClickType
from databricks_cli.version import print_version_callback, version
from databricks_cli.pipelines.api import PipelinesApi
from databricks_cli.configure.config import provide_api_client, profile_option, debug_option
from databricks_cli.utils import pipelines_exception_eater, CONTEXT_SETTINGS, pretty_format, \
    error_and_quit

try:
    json_parse_exception = json.decoder.JSONDecodeError
except AttributeError:  # Python 2
    json_parse_exception = ValueError

PIPELINE_ID_PERMITTED_CHARACTERS = set(string.ascii_letters + string.digits + '-_')


@click.command(context_settings=CONTEXT_SETTINGS,
               short_help='Creates a pipeline according to the pipeline settings.')
@click.argument('settings_arg', default=None, required=False)
@click.option('--settings', default=None,
              type=PipelineSettingClickType(), help=PipelineSettingClickType.help)
@click.option('--allow-duplicate-names', is_flag=True,
              help="If true, skips duplicate name checking while creating the pipeline.")
@debug_option
@profile_option
@pipelines_exception_eater
@provide_api_client
def create_cli(api_client, settings_arg, settings, allow_duplicate_names):
    """
    Creates a pipeline according to the pipeline settings. The pipeline settings are a
    JSON document that defines a Delta Live Tables pipeline on Databricks.

    If a pipeline with the same name already exists, pipeline will not be created.
    This check can be disabled by adding the --allow-duplicate-names option.

    If the pipeline settings contain an "id" field, this command will fail.

    Usage:

    databricks pipelines create example.json

    OR

    databricks pipelines create --settings example.json
    """
    if bool(settings_arg) == bool(settings):
        raise ValueError('Settings should be provided either as an argument ' +
                         '(Eg: databricks pipelines create example.json) or as ' +
                         'an option (Eg: databricks pipelines create --settings example.json).')

    src = settings_arg if bool(settings_arg) else settings
    settings_obj = _read_settings(src)
    settings_dir = os.path.dirname(src)
    try:
        response = PipelinesApi(api_client).create(
            settings_obj, settings_dir, allow_duplicate_names)
    except requests.exceptions.HTTPError as e:
        _handle_duplicate_name_exception(settings_obj, e, is_create_pipeline=True)

    new_pipeline_id = response['pipeline_id']
    click.echo("Successfully created pipeline: {} with ID: {}".format(
        _get_pipeline_url(api_client, new_pipeline_id), new_pipeline_id))


@click.command(context_settings=CONTEXT_SETTINGS,
               short_help='Edits a pipeline with the given pipeline settings.')
@click.argument('settings_arg', default=None, required=False)
@click.option('--settings', default=None, type=PipelineSettingClickType(),
              help=PipelineSettingClickType.help)
@click.option('--pipeline-id', default=None, type=PipelineIdClickType(),
              help=PipelineIdClickType.help)
@click.option('--allow-duplicate-names', is_flag=True,
              help="Skip duplicate name check while editing pipeline.")
@debug_option
@profile_option
@pipelines_exception_eater
@provide_api_client
def edit_cli(api_client, settings_arg, settings, pipeline_id, allow_duplicate_names):
    """
    Edits a pipeline according to the pipeline settings. The pipeline settings are a
    JSON document that defines a Delta Live Tables pipeline on Databricks.

    If another pipeline with the same name exists, pipeline settings will not be edited.
    This check can be disabled by adding the --allow-duplicate-names option.

    Note that if an ID is both specified in the settings and passed via --pipeline-id,
    the two ids must be the same, or the command will fail.

    Usage:

    databricks pipelines edit example.json

    OR

    databricks pipelines edit --settings example.json
    """
    if bool(settings_arg) == bool(settings):
        raise ValueError('Settings should be provided either as an argument ' +
                         '(Eg: databricks pipelines edit example.json) or as ' +
                         'an option (Eg: databricks pipelines edit --settings example.json).')

    src = settings_arg if bool(settings_arg) else settings
    settings_obj = _read_settings(src)
    settings_dir = os.path.dirname(src)

    if (pipeline_id and 'id' in settings_obj) and pipeline_id != settings_obj["id"]:
        raise ValueError(
            "The ID provided in --pipeline_id '{}' is different from the ID provided "
            "in the settings '{}'. Resolve the conflict and try the command again. ".format(
                pipeline_id, settings_obj["id"])
        )

    settings_obj['id'] = pipeline_id or settings_obj.get('id', None)
    _validate_pipeline_id(settings_obj['id'])

    try:
        PipelinesApi(api_client).edit(settings_obj, settings_dir, allow_duplicate_names)
    except requests.exceptions.HTTPError as e:
        _handle_duplicate_name_exception(settings_obj, e, is_create_pipeline=False)
    click.echo("Successfully edited pipeline settings: {}".format(
        _get_pipeline_url(api_client, settings_obj['id'])))


@click.command(context_settings=CONTEXT_SETTINGS,
               short_help='[Deprecated] This command is deprecated, use create and edit '
                          'commands instead.\n Deploys a delta pipeline according to the '
                          'pipeline settings.')
@click.argument('settings_arg', default=None, required=False)
@click.option('--settings', default=None, type=PipelineSettingClickType(),
              help=PipelineSettingClickType.help)
@click.option('--spec', default=None, type=PipelineSpecClickType(),
              help=PipelineSpecClickType.help)
@click.option('--allow-duplicate-names', is_flag=True,
              help="Skip duplicate name check while deploying pipeline")
@click.option('--pipeline-id', default=None, type=PipelineIdClickType(),
              help=PipelineIdClickType.help)
@debug_option
@profile_option
@pipelines_exception_eater
@provide_api_client
def deploy_cli(api_client, settings_arg, settings, spec, allow_duplicate_names, pipeline_id):
    """
    [Deprecated] This command is deprecated, use create and edit commands instead.

    Deploys a pipeline according to the pipeline settings. The pipeline settings are a
    JSON document that defines a Delta Live Tables pipeline on Databricks

    If the pipeline settings contains an "id" field, or if a pipeline ID is specified directly
    (using the  --pipeline-id argument), attempts to update an existing pipeline
    with that ID. If it does not, creates a new pipeline and logs the ID of the new pipeline
    to STDOUT. Note that if an ID is both specified in the settings and passed via --pipeline-id,
    the two IDs must be the same, or the command will fail.

    The deploy command will not create a new pipeline if a pipeline with the same name already
    exists. This check can be disabled by adding the --allow-duplicate-names option.

    Usage:

    databricks pipelines deploy example.json

    OR

    databricks pipelines deploy --settings example.json

    OR

    databricks pipelines deploy --pipeline-id 1234 --settings example.json
    """
    click.echo("DeprecationWarning: the \"deploy\" command is deprecated, " +
               "use \"create\" command to create a new pipeline or \"edit\" command " +
               "to modify an existing pipeline.\n")

    settings_error_msg = 'Settings should be provided either as an argument ' \
                         '(Eg: databricks pipelines deploy example.json) or as ' \
                         'an option (Eg: databricks pipelines deploy --settings example.json).'
    if bool(spec):
        if bool(spec) == bool(settings):
            raise ValueError(settings_error_msg)
        settings = spec

    if bool(settings_arg) == bool(settings):
        raise ValueError(settings_error_msg)

    src = settings_arg if bool(settings_arg) else settings
    settings_obj = _read_settings(src)
    settings_dir = os.path.dirname(src)
    if not pipeline_id and 'id' not in settings_obj:
        try:
            response = PipelinesApi(api_client).create(
                settings_obj, settings_dir, allow_duplicate_names)
        except requests.exceptions.HTTPError as e:
            _handle_duplicate_name_exception(settings_obj, e, is_create_pipeline=True)

        new_pipeline_id = response['pipeline_id']
        click.echo("Successfully created pipeline: {} with ID: {}".format(
            _get_pipeline_url(api_client, new_pipeline_id), new_pipeline_id))
    else:
        if (pipeline_id and 'id' in settings_obj) and pipeline_id != settings_obj["id"]:
            raise ValueError(
                "The ID provided in --pipeline_id '{}' is different from the ID provided "
                "in the settings '{}'. Resolve the conflict and try the command again. ".format(
                    pipeline_id, settings_obj["id"])
            )

        settings_obj['id'] = pipeline_id or settings_obj.get('id', None)
        _validate_pipeline_id(settings_obj['id'])
        try:
            PipelinesApi(api_client).edit(
                settings_obj, settings_dir, allow_duplicate_names)
        except requests.exceptions.HTTPError as e:
            _handle_duplicate_name_exception(settings_obj, e, is_create_pipeline=False)
        click.echo("Successfully deployed pipeline: {}".format(
            _get_pipeline_url(api_client, settings_obj['id'])))


@click.command(context_settings=CONTEXT_SETTINGS,
               short_help='Deletes the pipeline and cancels active update if one exists.')
@click.option('--pipeline-id', default=None, type=PipelineIdClickType(),
              help=PipelineIdClickType.help)
@debug_option
@profile_option
@pipelines_exception_eater
@provide_api_client
def delete_cli(api_client, pipeline_id):
    """
    Deletes the pipeline and cancels active update if one exists.

    Usage:

    databricks pipelines delete --pipeline-id 1234
    """
    _validate_pipeline_id(pipeline_id)
    PipelinesApi(api_client).delete(pipeline_id)
    click.echo("Pipeline {} deleted".format(pipeline_id))


@click.command(context_settings=CONTEXT_SETTINGS,
               short_help='Gets a pipeline\'s current settings and status.')
@click.option('--pipeline-id', default=None, type=PipelineIdClickType(),
              help=PipelineIdClickType.help)
@debug_option
@profile_option
@pipelines_exception_eater
@provide_api_client
def get_cli(api_client, pipeline_id):
    """
    Gets a pipeline's current settings and status.

    Usage:

    databricks pipelines get --pipeline-id 1234
    """
    _validate_pipeline_id(pipeline_id)
    click.echo(pretty_format(PipelinesApi(api_client).get(pipeline_id)))


@click.command(context_settings=CONTEXT_SETTINGS,
               short_help='Lists all pipelines and their statuses.')
@debug_option
@profile_option
@pipelines_exception_eater
@provide_api_client
def list_cli(api_client):
    """
    Lists all pipelines and their statuses.

    Usage:

    databricks pipelines list
    """
    click.echo(pretty_format(PipelinesApi(api_client).list()))


@click.command(context_settings=CONTEXT_SETTINGS,
               short_help='[Deprecated] Use the "start --full-refresh" command instead. ' +
                          'Resets a pipeline so that data can be reprocessed ' +
                          'from the beginning.')
@click.option('--pipeline-id', default=None, type=PipelineIdClickType(),
              help=PipelineIdClickType.help)
@debug_option
@profile_option
@pipelines_exception_eater
@provide_api_client
def reset_cli(api_client, pipeline_id):
    """
    [Deprecated] Use the "start --full-refresh" command instead.

    Resets a pipeline by truncating tables and creating new checkpoint folders so that data is
    reprocessed from the beginning.

    Usage:

    databricks pipelines reset --pipeline-id 1234
    """
    click.echo("DeprecationWarning: the \"reset\" command is deprecated, " +
               "use the \"start --full-refresh\" command instead.")
    _validate_pipeline_id(pipeline_id)
    resp = PipelinesApi(api_client).start_update(pipeline_id, full_refresh=True)
    click.echo(_gen_start_update_msg(resp, pipeline_id, True))


@click.command(context_settings=CONTEXT_SETTINGS,
               short_help='[Deprecated] Use the "start" command instead. ' +
                          'Starts a pipeline update.')
@click.option('--pipeline-id', default=None, type=PipelineIdClickType(),
              help=PipelineIdClickType.help)
@debug_option
@profile_option
@pipelines_exception_eater
@provide_api_client
def run_cli(api_client, pipeline_id):
    """
    [Deprecated] Use the "start" command instead.

    Starts a pipeline update.

    Usage:

    databricks pipelines run --pipeline-id 1234
    """
    click.echo("Deprecation warning: the \"run\" command is deprecated." +
               " Use the \"start\" command instead.")
    _validate_pipeline_id(pipeline_id)
    resp = PipelinesApi(api_client).start_update(pipeline_id, full_refresh=False)
    click.echo(_gen_start_update_msg(resp, pipeline_id, False))


@click.command(context_settings=CONTEXT_SETTINGS,
               short_help='Starts a pipeline update.')
@click.option('--pipeline-id', default=None, type=PipelineIdClickType(),
              help=PipelineIdClickType.help)
@click.option('--full-refresh', default=False, type=bool, is_flag=True,
              help='If present, truncates tables and creates new checkpoint ' +
                   'folders so that data is reprocessed from the beginning.')
@debug_option
@profile_option
@pipelines_exception_eater
@provide_api_client
def start_cli(api_client, pipeline_id, full_refresh):
    """
    Starts a pipeline update.

    Usage:

    databricks pipelines start --pipeline-id 1234 --full-refresh
    """
    _validate_pipeline_id(pipeline_id)
    resp = PipelinesApi(api_client).start_update(pipeline_id, full_refresh=full_refresh)
    click.echo(_gen_start_update_msg(resp, pipeline_id, full_refresh))


@click.command(context_settings=CONTEXT_SETTINGS,
               short_help='Stops the pipeline by cancelling any active update.')
@click.option('--pipeline-id', default=None, type=PipelineIdClickType(),
              help=PipelineIdClickType.help)
@debug_option
@profile_option
@pipelines_exception_eater
@provide_api_client
def stop_cli(api_client, pipeline_id):
    """
    Stops the pipeline by cancelling any active update.

    Usage:

    databricks pipelines stop --pipeline-id 1234
    """
    _validate_pipeline_id(pipeline_id)
    PipelinesApi(api_client).stop(pipeline_id)
    click.echo("Stopped pipeline {}.".format(pipeline_id))


def _gen_start_update_msg(resp, pipeline_id, full_refresh):
    output_msg = "Started an update "
    if resp and 'update_id' in resp:
        output_msg += "{} ".format(resp.get('update_id'))

    if full_refresh:
        output_msg += "with full refresh "

    output_msg += "for pipeline {}.".format(pipeline_id)
    return output_msg


def _read_settings(src):
    """
    Reads the settings at src as a JSON if no file extension is provided,
    or if in the extension format if the format is supported.
    """
    extension = os.path.splitext(src)[1]
    if extension.lower() == '.json':
        try:
            with open(src, 'r') as f:
                data = f.read()
            return json.loads(data)
        except json_parse_exception as e:
            error_and_quit("Invalid JSON provided in settings\n{}".format(e))
    else:
        raise ValueError('The provided file extension for the settings is not supported. ' +
                         'Only JSON files are supported.')


def _get_pipeline_url(api_client, pipeline_id):
    base_url = "{0.scheme}://{0.netloc}/".format(urlparse(api_client.url))
    return urljoin(base_url, "#joblist/pipelines/{}".format(pipeline_id))


def _validate_pipeline_id(pipeline_id):
    """
    Checks if the pipeline ID is not empty.
    """
    if pipeline_id is None or len(pipeline_id) == 0:
        error_and_quit(u'Empty pipeline ID provided')


def _handle_duplicate_name_exception(settings, exception, is_create_pipeline):
    error_code = None
    try:
        error_code = json.loads(exception.response.text).get('error_code')
    except ValueError:
        pass

    if error_code == 'RESOURCE_CONFLICT':
        if is_create_pipeline:
            raise ValueError(
                "Pipeline with name '{}' already exists. ".format(settings['name']) +
                "If you are updating an existing pipeline, use \"edit\" command. "
                "Otherwise, You can use the --allow-duplicate-names option to skip "
                "this check. ")
        else:
            raise ValueError(
                "Pipeline with name '{}' already exists. ".format(settings['name']) +
                "You can use the --allow-duplicate-names option to skip this check. ")

    raise exception


@click.group(context_settings=CONTEXT_SETTINGS,
             short_help='Utility to interact with Databricks Delta Live Tables Pipelines.')
@click.option('--version', '-v', is_flag=True, callback=print_version_callback,
              expose_value=False, is_eager=True, help=version)
@debug_option
@profile_option
def pipelines_group():  # pragma: no cover
    """
    Utility to interact with Databricks Delta Live Tables Pipelines.
    """
    pass


pipelines_group.add_command(deploy_cli, name='deploy')
pipelines_group.add_command(create_cli, name="create")
pipelines_group.add_command(edit_cli, name="edit")
pipelines_group.add_command(delete_cli, name='delete')
pipelines_group.add_command(get_cli, name='get')
pipelines_group.add_command(list_cli, name='list')
pipelines_group.add_command(start_cli, name='start')
pipelines_group.add_command(stop_cli, name='stop')

# DEPRECATED and will be removed in future versions.
pipelines_group.add_command(reset_cli, name='reset')
pipelines_group.add_command(run_cli, name='run')
