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

    <table>
        <thead>
            <tr>

            </tr>
        </thead>
        <tbody>
            %for job in jobs:
            <tr class="job-list-item ">
                <div class="field-id inline code">
                    <a href="${util.get_job_link(job.id, query='f=html')}">${job.id}</a>
                </div>
                %if job.get("title"):
                    <span class="dash">&#8212;</span>
                    <span class="field-title">${job.title}</span>
                %endif
                <div class="format-link">
                    (<a href="${util.get_job_link(job.id, query='f=json')}">OGC JSON</a>,
                     <a href="${util.get_job_link(job.id, query='f=xml')}">WPS XML</a>)
                </div>
            </tr>
        </tbody>
    </table>

</div>
