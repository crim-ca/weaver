<h2>Processes</h2>
<div class="process-listing">
    <dl>
        %for process in processes:
        <dt>${process.id}</dt>
        <dd>
            ${process.description}
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
