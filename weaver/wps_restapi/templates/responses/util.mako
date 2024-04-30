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
%for meta in metadata:
    <dt>
        ${meta.title}
    </dt>
    <dd>
        %if "href" in meta:
            <a href="${meta.href}">${meta.href}</a>
        %else:
            <div class="code">${meta.value}</div>
        %endif
        %if "lang" in meta:
            <div class="field">
                <div class="field-title">Language:</div>
                &nbsp;
                <div class="language">${meta.lang}</div>
            </div>
        %elif "hreflang" in meta:
            <div class="field">
                <div class="field-title">Language:</div>
                &nbsp;
                <div class="language">${meta.hreflang}</div>
            </div>
        %endif
        %if "role" in meta:
            <div class="field">
                <div class="field-title">Role:</div>
                &nbsp;
                <div class="code">${meta.role}</div>
            </div>
        %endif
        %if "type" in meta:
            <div class="field">
                <div class="field-title">Media-Type:</div>
                &nbsp;
                <div class="code">${meta.type}</div>
            </div>
        %endif
    </dd>
%endfor
</dl>
</%def>


<%def name="render_links(links)">
<dl>
%for link in links:
    <dt>
        <div class="label code">${link.rel}</div>
    </dt>
    <dd>
        %if "title" in link:
            <div class="description">${link.title}</div>
        %endif
        <a href="${link.href}">${link.href}</a>
        %if "hreflang" in link:
            <div class="field">
                <div class="field-title">Language:</div>
                &nbsp;
                <div class="language">${link.hreflang}</div>
            </div>
        %endif
        %if "type" in link:
            <div class="field">
                <div class="field-title">Media-Type:</div>
                &nbsp;
                <div class="code">${link.type}</div>
            </div>
        %endif
    </dd>
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
