<%inherit file="weaver.wps_restapi:templates/responses/base.mako"/>

<h2>Processes</h2>

<%def name="get_process_link(process)">
    ${weaver.wps_restapi_url}/processes/${process.id}
</%def>

<div class="process-listing">
    <div>
    Total processes: ${total}
    </div>
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
