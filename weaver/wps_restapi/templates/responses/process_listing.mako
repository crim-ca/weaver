<%inherit file="weaver.wps_restapi:templates/responses/base.mako"/>
<%namespace name="util" file="weaver.wps_restapi:templates/responses/util.mako"/>

<%block name="breadcrumbs">
<li><a href="${weaver.wps_restapi_url}?f=html">Home</a></li>
<li><a href="${util.get_processes_link(query='f=html')}">Processes</a></li>
</%block>

<h2 id="processes" class="page-title">
    <a href="#processes">Processes</a>
</h2>

<div class="format-link">
(<a href="${util.get_processes_link(query='f=json')}">JSON</a>)
</div>

<div class="process-listing">

    <div class="content-section nav-menu">
        <ul>
            <li>
                <div class="nav-link">
                    Return to <a href="${weaver.wps_restapi_url}?f=html">API Frontpage</a>
                </div>
            </li>
            ${util.get_paging_links()}
        </ul>
    </div>

    <div class="content-section">

    <div>
    Total processes: ${total}
    </div>

    <dl>
        %for process in processes:
        <dt class="process-list-item ">
            <div class="field-id inline code">
                <a href="${util.get_process_link(process.id, query='f=html')}">${process.id}</a>
            </div>
            %if process.get("title"):
                <span class="dash">&#8212;</span>
                <span class="field-title">${process.title}</span>
            %endif
            <div class="format-link">
                (<a href="${util.get_process_link(process.id, query='f=json')}">OGC JSON</a>,
                 <a href="${util.get_process_link(process.id, query='f=xml')}">WPS XML</a>)
            </div>
        </dt>
        <dd>
            %if process.get("description"):
                <div class="field">
                    <div class="field-key">Description:</div>
                    <div class="field-description">${process.description}</div>
                </div>
            %endif
            %if process.version:
                <div class="field">
                    <div class="field-key">Version:</div>
                    <div class="label label-info version-tag">${process.version}</div>
                </div>
            %endif
            %if process.keywords:
                <div class="field">
                    <div class="field-key">Keywords:</div>
                    %for keyword in process.keywords:
                        <div class="label label-note">${keyword}</div>
                    %endfor
                </div>
            %endif
        </dd>
        %endfor
    </dl>

</div>
