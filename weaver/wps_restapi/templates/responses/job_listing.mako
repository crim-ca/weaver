<%inherit file="weaver.wps_restapi:templates/responses/base.mako"/>
<%namespace name="util" file="weaver.wps_restapi:templates/responses/util.mako"/>

<%block name="breadcrumbs">
<li><a href="${weaver.wps_restapi_url}?f=html">Home</a></li>
<li><a href="${util.get_jobs_link(query='f=html')}">Jobs</a></li>
</%block>

<h2 id="jobs" class="page-title">
    <a href="#jobs">Jobs</a>
</h2>

<div class="format-link">
(<a href="${util.get_jobs_link(query='f=json')}">JSON</a>)
</div>

<div class="job-listing">

    <div class="content-section nav-menu">
        <ul>
            <li>
                <div class="nav-link">
                    Return to <a href="${weaver.wps_restapi_url}?f=html">API Frontpage</a>.
                </div>
            </li>
            ${util.get_paging_links()}
        </ul>
    </div>

    <div class="content-section">

    <div>
        Total jobs: ${total}
    </div>

    <table class="table-jobs">
        <thead>
            <tr>
                <th>Job ID</th>
                <th>Process ID</th>
                <th>Provider ID</th>
                <th>Status</th>
                <th>Progress</th>
                <th>Duration</th>
                <th>Created</th>
                <th>Started</th>
                <th>Updated</th>
                <th>Finished</th>
                <th>Message</th>
            </tr>
        </thead>
        <tbody>
            %for job in jobs:
            <tr class="job-list-item ">
                <td class="table-jobs-field code">
                    <a href="${util.get_job_link(job.jobID, query='f=html')}">${job.jobID}</a>
                </td>
                <td class="table-jobs-field code">
                    <a
                        href="${util.get_process_link(job.processID, job.providerID, query='f=html')}"
                    >${job.processID}</a>
                </td>
                <td class="table-jobs-field code">
                    %if job.providerID:
                        <a
                            href="${util.get_provider_link(job.providerID, query='f=html')}"
                        >${job.providerID}</a>
                    %else:
                        <span class="undefined"><abbr title="Local Process">n/a</abbr></span>
                    %endif
                </td>
                <td class="table-jobs-field">
                    ${util.render_status(job.status)}
                </td>
                <td class="table-jobs-field">
                    ${util.render_progress(job.progress, job.status)}
                </td>
                <td class="table-jobs-field code">
                    ${job.duration}
                </td>
                %for field in ["created", "started", "updated", "finished"]:
                <td class="table-jobs-field code">
                    ${job.get(field) or "n/a"}
                </td>
                %endfor
                <td class="table-jobs-field">
                    ${job.message}
                </td>
            </tr>
            %endfor
        </tbody>
    </table>

</div>
