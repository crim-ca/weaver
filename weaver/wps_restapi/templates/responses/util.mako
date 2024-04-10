<!---
Utilities for rendering elements in other pages.
-->

<%def name="get_processes_link(query='')">
    ${weaver.wps_restapi_url}/processes${f"?{query}" if query else ""}
</%def>


<%def name="get_process_link(process, query='')">
    ${weaver.wps_restapi_url}/processes/${process}${f"?{query}" if query else ""}
</%def>


<%def name="render_metadata(metadata)">
<dl>
%for meta in process.metadata:
    <dt>
        ${meta.title}
        %if "lang" in meta:
            <div class="language">${meta.lang}</div>
        %elif "hreflang" in meta:
            <div class="language">${meta.hreflang}</div>
        %endif
        %if "role" in meta:
            <div class="code">${meta.role}</div>
        %endif
        %if "type" in meta:
            <div class="code">${meta.type}</div>
        %endif
    </dt>
    %if "href" in meta:
        <dd>
            ${meta.href}

        </dd>
    %else:
        <dd>
            ${meta.value}
        </dd>
    %endif
%endfor
</dl>
</%def>


<!--
Requirements for rendering JSON contents.
-->
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/10.4.0/styles/default.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/10.4.0/highlight.min.js"></script>
<script charset="UTF-8" src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/10.4.0/languages/json.min.js"></script>
<script charset="UTF-8" src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/10.4.0/languages/yaml.min.js"></script>
<script>hljs.initHighlightingOnLoad();</script>
<!--
WARNING: newlines matter between 'pre', they will add extra whitespace. Leave them on the same line.
-->
<%def name="render_json(json_data)">
    <pre><code class="language-json">${json_data}</code></pre>
</%def>


<%def name="render_input(input_id, input_data)">
<div class="process-input">
    ${render_json(input_data)}
</div>
</%def>


<%def name="render_output(output_id, output_data)">
<div class="process-output">
    ${render_json(output_data)}
</div>
</%def>
