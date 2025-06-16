function updateSelectedItems(name, dopost) {
  const selected = [];
  $('.multi-check-'+name+':checked').each(function () {
    selected.push($(this).val());
  });
  $('#selected_'+name).val(JSON.stringify(selected));
  if (dopost) {
      postMain(true);
  }
}

function updateMultiCheck(obj, name) {
    const isExclusive = $(obj).data('exclusive') === true || $(obj).data('exclusive') === "true";
    if (isExclusive && obj.checked) {
      $('.multi-check-'+name).not(obj).prop('checked', false);
    } else if (obj.checked) {
      $('.multi-check-'+ name+'[data-exclusive="true"]').prop('checked', false);
    }
    updateSelectedItems(name, true);
}

function initializeMultiCheck() {
  $('.multi-check-status').on('change', function () {
   updateMultiCheck(this, 'status');
  });
  $('.multi-check-group').on('change', function () {
   updateMultiCheck(this, 'group');
  });
  $('.multi-check-provider').on('change', function () {
   updateMultiCheck(this, 'provider');
  });

  // Inizializza selezioni
  updateSelectedItems('status', false);
  updateSelectedItems('group', false);
  updateSelectedItems('provider', false);
}
