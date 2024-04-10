<%inherit file="weaver.wps_restapi:templates/responses/base.mako"/>
<%namespace name="util" file="weaver.wps_restapi:templates/responses/util.mako"/>

<h2>Process: ${id}</h2>

<div class="format-link">
    (<a href="${util.get_process_link(id, query='f=json')}">OGC JSON</a>,
     <a href="${util.get_process_link(id, query='f=xml')}">WPS XML</a>)
</div>

<ul>
    <li>
        <div class="nav-link">
        Return to <a href="${util.get_processes_link(query='f=html')}">processes listing</a>.
        </div>
    </li>
    <li>
        <div class="nav-link">
        <a href="#metadata">Process Metadata</a>
        </div>
    </li>
    <li>
        <div class="nav-link">
        <a href="#inputs">Process Inputs</a>
        </div>
    </li>
    <li>
        <div class="nav-link">
        <a href="#outputs">Process Outputs</a>
        </div>
    </li>
    <li>
        <div class="nav-link">
        <a href="#links">Process Links</a>
        </div>
    </li>
</ul>

<div class="process-description">

    <div class="content-section">
    %if title:
        <span class="title">${title}</span>
    %endif
    %if description:
        <span class="description">${description}</span>
    %else:
        <span class="description undefined">No description available.</span>
    %endif
    </div>

    <h3 id="metadata">
        <a href="#metadata">Metadata</a>
    </h3>
    <div class="content-section">
    %if metadata:
        ${util.render_metadata(metadata)}
    %else:
        <span class="undefined">No metadata provided.</span>
    %endif
    </div>

    <h3 id="inputs">
        <a href="#inputs">Inputs</a>
    </h3>
    <div class="content-section">
    %for input_id, input_data in inputs.items():
        ${util.render_input(input_id, input_data)}
    %endfor
    </div>

    <h3 id="outputs">
        <a href="#outputs">Outputs</a>
    </h3>
    <div class="content-section">
    %for output_id, output_data in outputs.items():
        ${util.render_output(output_id, output_data)}
    %endfor
    </div>

    <h3 id="links">
        <a href="#links">Links</a>
    </h3>
</div>
