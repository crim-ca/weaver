<%inherit file="weaver.wps_restapi:templates/responses/base.mako"/>
<%namespace name="util" file="weaver.wps_restapi:templates/responses/util.mako"/>

<h2>Processes</h2>

<div class="format-link">
(<a href="${util.get_processes_link(query='f=json')}">JSON</a>)
</div>

<div class="process-listing">

    <div class="content-section">
    Total processes: ${total}
    </div>

    <div class="content-section">
    <dl>
        %for process in processes:
        <dt class="process-list-item ">
            <a href="${util.get_process_link(process.id, query='f=html')}">${process.id}</a>
            %if process.get("title"):
                <span class="title">${process.title}</span>
            %endif
            <div class="format-link">
                (<a href="${util.get_process_link(process.id, query='f=json')}">OGC JSON</a>,
                 <a href="${util.get_process_link(process.id, query='f=xml')}">WPS XML</a>)
            </div>
        </dt>
        <dd>
            %if process.get("description"):
                <div class="field">
                    <span class="description">${process.description}</span>
                </div>
            %endif
            %if process.version:
                <div class="field">
                    <div class="field-title">Version:</div>
                    &nbsp;
                    <div class="label label-info version-tag">${process.version}</div>
                </div>
            %endif
            %if process.keywords:
                <div class="field">
                    <div class="field-title">Keywords:</div>
                    &nbsp;
                    %for keyword in process.keywords:
                        <div class="label label-note">${keyword}</div>
                    %endfor
                </div>
            %endif
        </dd>
        %endfor
    </dl>
    </div>

</div>
