<%inherit file="weaver.wps_restapi:templates/responses/base.mako"/>
<%namespace name="util" file="weaver.wps_restapi:templates/responses/util.mako"/>

<%block name="breadcrumbs">
<li><a href="${weaver.wps_restapi_url}?f=html">Home</a></li>
<li><a href="${util.get_jobs_link(query='f=html')}">Jobs</a></li>
<li><a href="${util.get_job_link(job.id, query='f=html')}">Job [${job.id}]</a></li>
</%block>

<h2 id="job-status" class="page-title">
    <a href="#job-status">Job Status</a>
</h2>

<div class="format-link">
    (<a href="${util.get_job_link(job.id, query='f=json&profile=OGC')}">JSON OGC</a>,
     <a href="${util.get_job_link(job.id, query='f=json&profile=openEO')}">JSON openEO</a>)
</div>

<div class="job-status">

    <div class="content-section nav-menu">
        <ul>
            <li>
                <div class="nav-link">
                    Return to <a href="${weaver.wps_restapi_url}?f=html">API Frontpage</a>.
                </div>
            </li>
            <li>
                <div class="nav-link">
                    Return to <a href="${util.get_jobs_link(query='f=html')}">Jobs list</a>.
                </div>
            </li>
            <li>
                <div class="nav-link">
                    Go to <a href="#metadata">Job Metadata</a>
                </div>
            </li>
            <li>
                <div class="nav-link">
                    Go to <a href="#results">Job Results</a>
                </div>
            </li>
            <li>
                <div class="nav-link">
                    Go to <a href="#statistics">Job Statistics</a>
                </div>
            </li>
            <li>
                <div class="nav-link">
                    Go to <a href="#logs">Job Logs</a>
                </div>
            </li>
            <li>
                <div class="nav-link">
                    Go to <a href="#errors">Job Errors</a>
                </div>
            </li>
            <li>
                <div class="nav-link">
                    Go to <a href="#provenance">Job Provenance</a>
                </div>
            </li>
            ${util.get_paging_links()}
        </ul>
    </div>

    <div class="content-section">
        <h3 id="metadata">
            <a href="#metadata">Metadata</a>
        </h3>
        <table class="table-job-status">
            <tr class="table-job-status-item ">
                <td class="table-job-status-field field-key">Job ID</td>
                <td class="table-job-status-field code">${job.id}</td>
            </tr>
            <tr class="table-job-status-item ">
                <td class="table-job-status-field field-key">Process ID</td>
                <td class="table-job-status-field code">
                    <a href="${util.get_process_link(job.process, job.service, query='f=html')}"
                    >${job.process}</a>
                </td>
            </tr>
            <tr class="table-job-status-item ">
                <td class="table-job-status-field field-key">Provider ID</td>
                <td class="table-job-status-field code">
                    %if job.service:
                        <a
                            href="${util.get_provider_link(job.service, query='f=html')}"
                        >${job.service}</a>
                    %else:
                        <span class="undefined"><abbr title="Local Process">n/a</abbr></span>
                    %endif
                </td>
            </tr>
            <tr class="table-job-status-item ">
                <td class="table-job-status-field field-key">Status</td>
                <td class="table-job-status-field">
                    ${util.render_status(status)}
                </td>
            </tr>
            <tr class="table-job-status-item ">
                <td class="table-job-status-field field-key">Message</td>
                <td class="table-job-status-field">
                    ${message}
                </td>
            </tr>
            <tr class="table-job-status-item ">
                <td class="table-job-status-field field-key">Progress</td>
                <td class="table-job-status-field">
                    ${util.render_progress(job.progress, job.status)}
                </td>
            </tr>
            <tr class="table-job-status-item ">
                <td class="table-job-status-field field-key">Duration</td>
                <td class="table-job-status-field code">
                    ${job.duration}
                </td>
            </tr>
            %for field in ["created", "started", "updated", "finished"]:
            <tr class="table-job-status-item ">
                <td class="table-job-status-field field-key">${field.capitalize()}</td>
                <td class="table-job-status-field code">
                    %if job.get(field):
                        ${job.get(field)}
                    %else:
                        <span class="undefined">n/a</span>
                    %endif
                </td>
            </tr>
            %endfor
        </table>
    </div>

    <div class="content-section">
        <h3 id="inputs">
            <a href="#inputs">Inputs</a>
        </h3>
        <p>Submitted request input values and output parametrization for the job execution.</p>
        ${util.build_job_toggle_button_code(job, type="inputs", format="json", language="json")}
    </div>

    <div class="content-section">
        <h3 id="results">
            <a href="#results">Results</a>
        </h3>
        %if job.success:
            <p>Results produced by the job execution.</p>
            ${util.build_job_toggle_button_code(job, type="results", format="json", language="json")}
        %elif job.is_finished:
            <p>No results available. Job is not finished.</p>
        %else:
            <p>No results available. Job did not succeed.</p>
        %endif
    </div>

    <div class="content-section">
        <h3 id="job-logs">
            <a href="#job-logs">Logs</a>
        </h3>
        <p>Logs captured during the job execution.</p>
        ${util.build_job_toggle_button_code(job, type="logs", format="text", language="accesslog")}
    </div>

    <!-- fixme: if not success : error/exception -->
    <div class="content-section">
        <h3 id="errors">
            <a href="#errors">Errors</a>
        </h3>
        <p>Errors that occurred during the job execution.</p>
        <!-- fill data here -->
    </div>

    <div class="content-section">
        <h3 id="statistics">
            <a href="#statistics">Statistics</a>
        </h3>
        %if job.is_finished:
            <p>Statistics collected during the job execution.</p>
            ${util.build_job_toggle_button_code(job, type="statistics", format="json", language="json")}
        %else:
            <p>No statistics available. Job is not finished.</p>
        %endif
    </div>

    <div class="content-section">
        <h3 id="provenance">
            <a href="#provenance">Provenance</a>
        </h3>
        <p>Provenance metadata collected during the job execution request.</p>
        <!-- fill data here -->
    </div>

    <div class="content-section">
        <h3 id="links">
            <a href="#links">Links</a>
        </h3>
        ${util.render_links(links)}
    </div>

</div>
