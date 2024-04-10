<%inherit file="weaver.wps_restapi:templates/responses/base.mako"/>
<%inherit file="weaver.wps_restapi:templates/responses/util.mako"/>

<h2>Process: ${process.id}</h2>

<div class="format-link">
View <a href="${get_processes_link(query='f=json')}">JSON</a> representation.
</div>

<div class="process-description">
    <dl>
        %for process in processes:
        <dt>
            <a href="${get_process_link(process)}">${process.id}</a>
            %if process.get("title"):
                <span class="title">${process.title}</span>
            %endif
        </dt>
        <dd>
            %if process.get("description"):
                ${process.description}
            %endif
            %if process.version:
                <span class="version">${process.version}</span>
            %endif
            %if process.keywords:
            <br>
            <b>Keywords</b>: ${", ".join(process.keywords)}
            %endif
        </dd>
        %endfor
    </dl>
</div>
