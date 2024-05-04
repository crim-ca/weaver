<%inherit file="weaver.wps_restapi:templates/responses/base.mako"/>
<%namespace name="util" file="weaver.wps_restapi:templates/responses/util.mako"/>

<h2 id="id" class="page-title">
    <div class="process-title inline">
        <div>
            Process:
            <div class="field-id code inline">
                <a href="#id">${id}</a>
            </div>
        </div>
        %if version:
        <div class="label label-info version-tag code">${version}</div>
        %endif
    </div>
</h2>

<div class="format-link">
    (<a href="${util.get_process_link(id, query='f=json')}">OGC JSON</a>,
     <a href="${util.get_process_link(id, query='f=xml')}">WPS XML</a>)
</div>

<div class="content-section nav-menu">
    <ul>
        <li>
            <div class="nav-link">
                Return to <a href="${weaver.wps_restapi_url}?f=html">API Frontpage</a>.
            </div>
        </li>
        <li>
            <div class="nav-link">
                Return to <a href="${util.get_processes_link(query='f=html')}">Processes Listing</a>.
            </div>
        </li>
        <li>
            <div class="nav-link">
                Go to <a href="#metadata">Process Metadata</a>
            </div>
        </li>
        <li>
            <div class="nav-link">
                Go to <a href="#inputs">Process Inputs</a>
            </div>
        </li>
        <li>
            <div class="nav-link">
                Go to <a href="#outputs">Process Outputs</a>
            </div>
        </li>
        <li>
            <div class="nav-link">
                Go to <a href="#links">Process Links</a>
            </div>
        </li>
    </ul>
</div>

<div class="process-description">

    <div class="content-section">
    %if title:
        <span class="field-title">${title}</span>
    %endif
    %if description:
        <span class="field-description">${description}</span>
    %else:
        <span class="field-description undefined">No description available.</span>
    %endif
    </div>

    <div class="content-section">
        <h3 id="metadata">
            <a href="#metadata">Metadata</a>
        </h3>
        %if metadata:
            ${util.render_metadata(metadata)}
        %else:
            <span class="undefined">No metadata provided.</span>
        %endif
    </div>

    <div class="content-section">
        <h3 id="inputs">
            <a href="#inputs">Inputs</a>
        </h3>
        ${util.render_inputs(inputs)}
    </div>

    <div class="content-section">
        <h3 id="outputs">
            <a href="#outputs">Outputs</a>
        </h3>
        ${util.render_outputs(outputs)}
    </div>

    <div class="content-section">
        <h3 id="links">
            <a href="#links">Links</a>
        </h3>
        ${util.render_links(links)}
    </div>
</div>
