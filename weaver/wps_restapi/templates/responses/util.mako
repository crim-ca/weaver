<!---
Utilities for rendering elements in other pages.
-->

<%def name="get_processes_link(query='')">
    ${weaver.wps_restapi_url}/processes${f"?{query}" if query else ""}
</%def>


<%def name="get_process_link(process, query='')">
    ${weaver.wps_restapi_url}/processes/${process}${f"?{query}" if query else ""}
</%def>


<!--
Assume that the definitions will be inserted into a 'nav-menu' with a parent HTML list block.
-->
<%def name="get_paging_links()">
    <%
        next_page = None
        prev_page = None
        last_page = None
        first_page = None
        for link in body.get("links") or []:
            if link.rel == "prev":
                prev_page = link.href
            if link.rel == "next":
                next_page = link.href
            if link.rel == "last":
                last_page = link.href
            if link.rel == "first":
                first_page = link.href
    %>
    %if first_page:
        <li>
            <div class="nav-link">
                Go to <a href="${first_page}">first page</a>.
            </div>
        </li>
    %endif
    %if prev_page:
        <li>
            <div class="nav-link">
                Go to <a href="${prev_page}">previous page</a>.
            </div>
        </li>
    %endif
    %if next_page:
        <li>
            <div class="nav-link">
                Go to <a href="${next_page}">next page</a>.
            </div>
        </li>
    %endif
    %if last_page:
        <li>
            <div class="nav-link">
                Go to <a href="${last_page}">last page</a>.
            </div>
        </li>
    %endif
</%def>


<!--
WARNING: newlines matter between 'pre', they will add extra whitespace. Leave them on the same line.
NOTE: class 'language-json' used by the 'ajax/libs/highlight.js' library inserted in the head scripts.
-->
<%def name="render_json(json_data, indent=2, **kwargs)">
    <pre><code class="language-json">${json.dumps(json_data, indent=indent, **kwargs)}</code></pre>
</%def>


<%def name="render_bool(value)">
    <div class="code ${str(value).lower()}">
        ${str(value).lower()}
    </div>
</%def>


<%def name="render_metadata(metadata)">
<dl class="indent">
%for meta in metadata:
    <dt>
        ${meta.title}
    </dt>
    <dd>
        %if "href" in meta:
            <div class="code">
                <a href="${meta.href}">${meta.href}</a>
            </div>
        %else:
            <div class="code">${meta.value}</div>
        %endif
        %if "lang" in meta:
            <div class="field">
                <div class="field-key">Language:</div>
                <div class="language">${meta.lang}</div>
            </div>
        %elif "hreflang" in meta:
            <div class="field">
                <div class="field-key">Language:</div>
                <div class="language">${meta.hreflang}</div>
            </div>
        %endif
        %if "role" in meta:
            <div class="field">
                <div class="field-key">Role:</div>
                <div class="code">${meta.role}</div>
            </div>
        %endif
        %if "type" in meta:
            <div class="field indent">
                <div class="field-key">Media-Type:</div>
                <div class="code">${meta.type}</div>
            </div>
        %endif
    </dd>
%endfor
</dl>
</%def>


<%def name="render_links(links)">
<dl class="indent">
%for link in links:
    <dt>
        <div class="label code">${link.rel}</div>
    </dt>
    <dd>
        %if "title" in link:
            <div class="field-title">${link.title}</div>
        %endif
        <div class="code">
            <a href="${link.href}">${link.href}</a>
        </div>
        %if "hreflang" in link:
            <div class="field">
                <div class="field-key">Language:</div>
                <div class="language">${link.hreflang}</div>
            </div>
        %endif
        %if "type" in link:
            <div class="field">
                <div class="field-key">Media-Type:</div>
                <div class="code">${link.type}</div>
            </div>
        %endif
    </dd>
%endfor
</dl>
</%def>


<%def name="render_inputs(inputs)">
<dl class="indent">
%for input_id, input_data in inputs.items():
    <div class="process-input">
        <dt id="input-${input_id}">
            <div class="field-id inline code">
                <a href="#input-${input_id}">${input_id}</a>
            </div>
            %if "title" in input_data:
                <span class="dash">&#8212;</span>
                <span class="field-title">${input_data.title}</span>
            %endif
        </dt>
        <dd>
            %for field in ["description"]:
                %if field in input_data:
                <div class="field">
                    <div class="field-key field-sub">${field.capitalize()}:</div>
                    <div class="field-${field}">${input_data[field]}</div>
                </div>
                %endif
            %endfor
            <div class="field-key field-sub">Schema:</div>
            <div class="indent">
                <div class="inline">
                    <div class="field-key code">minOccurs = ${input_data.minOccurs}</div>
                    <div class="field-key">,</div>
                    <div class="field-key code">maxOccurs = ${input_data.maxOccurs}</div>
                </div>
                ${render_json(input_data.schema)}
            </div>
            <div class>
                <%
                    known_fields = {"title", "description", "schema", "minOccurs", "maxOccurs"}
                    extra_fields = set(input_data) - known_fields
                %>
                %if extra_fields:
                    <div class="field-key field-sub">Additional Details:</div>
                    <div class="indent">
                        %for field in extra_fields:
                            <div class="field-key field-extra">${field}:</div>
                            <div class="">${render_json(input_data[field])}</div>
                        %endfor
                    </div>
                %endif
            </div>
        </dd>
    </div>
%endfor
</dl>
</%def>


<%def name="render_outputs(outputs)">
<dl class="indent">
%for output_id, output_data in outputs.items():
    <div class="process-output">
        <dt id="output-${output_id}">
            <a href="#output-${output_id}">${output_id}</a>
        </dt>
        <dd>
            <div>
                <div class="field-key">Schema:</div>
                ${render_json(output_data.schema)}
            </div>
        </dd>
    </div>
%endfor
</dl>
</%def>
